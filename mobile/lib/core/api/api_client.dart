import 'dart:async';
import 'dart:math';

import 'package:dio/dio.dart';

import '../auth/token_store.dart';
import 'api_exception.dart';
import 'json.dart';
import 'models.dart';

/// HTTP transport for docs/API.md.
///
/// * Adds `X-App-Version` and the access token.
/// * Refreshes an expired access token once (one refresh at a time) and
///   replays the request.
/// * Retries only what is safe to repeat: GETs, and mutations that carry
///   an Idempotency-Key. Never login or refresh.
/// * Turns every failure into an [ApiException].
class ApiClient {
  ApiClient({required String baseUrl, required this.appVersion, required this.tokens, Dio? dio})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: baseUrl,
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 20),
              sendTimeout: const Duration(seconds: 20),
              responseType: ResponseType.json,
              contentType: Headers.jsonContentType,
            ),
          );

  final Dio _dio;
  final String appVersion;
  final TokenStore tokens;
  final _sessionEnded = StreamController<void>.broadcast();
  Future<bool>? _refreshing;
  final Random _jitter = Random();

  /// Fires when the login can't be recovered; the app returns to login.
  Stream<void> get sessionEnded => _sessionEnded.stream;

  static const maxRetries = 2;

  Future<Json> get(String path, {Map<String, Object?>? query, bool auth = true}) =>
      _send('GET', path, query: query, auth: auth);

  Future<Json> post(String path, {Object? body, String? idempotencyKey, bool auth = true}) =>
      _send('POST', path, body: body, idempotencyKey: idempotencyKey, auth: auth);

  Future<void> postNoContent(String path) async {
    await _send('POST', path);
  }

  Future<Json> _send(
    String method,
    String path, {
    Object? body,
    Map<String, Object?>? query,
    String? idempotencyKey,
    bool auth = true,
  }) async {
    var attempt = 0;
    var refreshed = false;
    while (true) {
      final current = auth ? await tokens.read() : null;
      try {
        final response = await _dio.request<Object?>(
          path,
          data: body,
          queryParameters: query,
          options: Options(
            method: method,
            headers: {
              'X-App-Version': appVersion,
              'Authorization': ?(current == null ? null : 'Bearer ${current.accessToken}'),
              'Idempotency-Key': ?idempotencyKey,
            },
          ),
        );
        final data = response.data;
        if (data == null || data == '') return const {};
        if (data is Map<String, Object?>) return data;
        throw const UnexpectedException();
      } on DioException catch (e) {
        final error = _map(e);
        if (auth && !refreshed && current != null && error is ServerRejection && error.code == 'UNAUTHENTICATED') {
          refreshed = true;
          if (await _refreshOnce()) continue;
          throw const SessionEndedException();
        }
        if (error is ServerRejection && error.code == 'SESSION_EXPIRED') {
          await _endSession();
          throw const SessionEndedException();
        }
        final retryable = error is OfflineException || (error is ServerRejection && error.isRetryableServerError);
        final repeatable = method == 'GET' || idempotencyKey != null;
        if (retryable && repeatable && attempt < maxRetries) {
          attempt++;
          await Future<void>.delayed(_backoff(attempt));
          continue;
        }
        throw error;
      }
    }
  }

  Duration _backoff(int attempt) {
    final base = attempt == 1 ? 1000 : 3000;
    return Duration(milliseconds: base + _jitter.nextInt(500));
  }

  Future<bool> _refreshOnce() => _refreshing ??= _refresh().whenComplete(() => _refreshing = null);

  Future<bool> _refresh() async {
    final current = await tokens.read();
    if (current == null) return false;
    try {
      final response = await _dio.post<Object?>(
        '/v1/auth/refresh',
        data: {'refresh_token': current.refreshToken},
        options: Options(headers: {'X-App-Version': appVersion}),
      );
      final data = response.data;
      if (data is! Map<String, Object?>) return false;
      await tokens.write(Tokens.fromJson(data.obj('tokens')));
      return true;
    } on DioException catch (e) {
      final error = _map(e);
      if (error is ServerRejection && error.status == 401) await _endSession();
      if (error is OfflineException) throw error;
      return false;
    } on FormatException {
      return false;
    }
  }

  Future<void> _endSession() async {
    await tokens.clear();
    _sessionEnded.add(null);
  }

  ApiException _map(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
      case DioExceptionType.connectionError:
        return const OfflineException();
      case DioExceptionType.cancel:
      case DioExceptionType.badCertificate:
      case DioExceptionType.unknown:
        return e.error is Exception && e.response == null ? const OfflineException() : const UnexpectedException();
      case DioExceptionType.badResponse:
        break;
    }
    final response = e.response;
    final status = response?.statusCode ?? 0;
    final data = response?.data;
    final error = data is Map<String, Object?> ? data['error'] : null;
    if (error is! Map<String, Object?>) {
      return status >= 500
          ? ServerRejection(status: status, code: 'SERVER_ERROR', message: const UnexpectedException().userMessage)
          : const UnexpectedException();
    }
    final code = error['code'] is String ? error['code']! as String : 'ERROR';
    final message = error['message'] is String ? error['message']! as String : const UnexpectedException().userMessage;
    switch (code) {
      case 'MAINTENANCE':
        final until = error['until'];
        return MaintenanceException(message, until is String ? DateTime.tryParse(until)?.toUtc() : null);
      case 'UPGRADE_REQUIRED':
        final url = error['download_url'];
        return UpgradeRequiredException(url is String ? url : null);
    }
    final rawFields = error['fields'];
    final fields = <String, String>{
      if (rawFields is Map<String, Object?>)
        for (final entry in rawFields.entries)
          if (entry.value is String) entry.key: entry.value! as String,
    };
    final retry = error['retry_after_seconds'];
    return ServerRejection(
      status: status,
      code: code,
      message: message,
      fields: fields,
      retryAfter: retry is int ? Duration(seconds: retry) : null,
    );
  }

  void close() {
    _sessionEnded.close();
    _dio.close();
  }
}
