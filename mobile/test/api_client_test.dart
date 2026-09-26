import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:future_fashion/core/api/api_client.dart';
import 'package:future_fashion/core/api/api_exception.dart';
import 'package:future_fashion/core/api/models.dart';
import 'package:future_fashion/core/auth/token_store.dart';

import 'support/fakes.dart';

/// Answers requests from a script and records what was sent.
class ScriptedAdapter implements HttpClientAdapter {
  ScriptedAdapter(this.script);

  final List<Object> script; // ResponseBody, or DioExceptionType for a network failure
  final requests = <RequestOptions>[];

  static ResponseBody json(int status, Object body, {Map<String, List<String>>? headers}) => ResponseBody.fromString(
    jsonEncode(body),
    status,
    headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType],
      ...?headers,
    },
  );

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    final next = script.removeAt(0);
    if (next is DioExceptionType) throw DioException(requestOptions: options, type: next);
    return next as ResponseBody;
  }

  @override
  void close({bool force = false}) {}
}

Map<String, Object?> errorBody(String code, [String message = 'msg']) => {
  'error': {'code': code, 'message': message, 'request_id': 'r1', 'retry_after_seconds': null, 'fields': null},
};

void main() {
  late MemoryTokenStore tokens;

  (ApiClient, ScriptedAdapter) make(List<Object> script) {
    final adapter = ScriptedAdapter(script);
    final dio = Dio(BaseOptions(baseUrl: 'https://api.test'))..httpClientAdapter = adapter;
    return (ApiClient(baseUrl: 'https://api.test', appVersion: '1.0.0', tokens: tokens, dio: dio), adapter);
  }

  setUp(() {
    tokens = MemoryTokenStore()..tokens = Tokens.fromJson(tokensJson());
  });

  test('sends the app version and the access token', () async {
    final (client, adapter) = make([ScriptedAdapter.json(200, meJson())]);
    await client.get('/v1/me');
    expect(adapter.requests.single.headers['X-App-Version'], '1.0.0');
    expect(adapter.requests.single.headers['Authorization'], 'Bearer ffa_test');
  });

  test('refreshes an expired access token once, then replays the request', () async {
    final (client, adapter) = make([
      ScriptedAdapter.json(401, errorBody('UNAUTHENTICATED')),
      ScriptedAdapter.json(200, {
        'tokens': {...tokensJson(), 'access_token': 'ffa_new', 'refresh_token': 'ffr_new'},
      }),
      ScriptedAdapter.json(200, meJson()),
    ]);
    final body = await client.get('/v1/me');
    expect(body['public_id'], '7Q2K9MXA');
    expect(adapter.requests.map((r) => r.path), ['/v1/me', '/v1/auth/refresh', '/v1/me']);
    expect(adapter.requests.last.headers['Authorization'], 'Bearer ffa_new');
    expect(tokens.tokens!.refreshToken, 'ffr_new');
  });

  test('a refused refresh ends the session and clears the tokens', () async {
    final (client, _) = make([
      ScriptedAdapter.json(401, errorBody('UNAUTHENTICATED')),
      ScriptedAdapter.json(401, errorBody('SESSION_EXPIRED')),
    ]);
    final ended = expectLater(client.sessionEnded, emits(null));
    await expectLater(client.get('/v1/me'), throwsA(isA<SessionEndedException>()));
    await ended;
    expect(tokens.tokens, isNull);
  });

  test('GETs are retried after a network failure', () async {
    final (client, adapter) = make([DioExceptionType.connectionError, ScriptedAdapter.json(200, meJson())]);
    await client.get('/v1/me');
    expect(adapter.requests, hasLength(2));
  }, timeout: const Timeout(Duration(seconds: 10)));

  test('mutations are retried only when they carry an idempotency key', () async {
    final (plain, plainAdapter) = make([DioExceptionType.connectionError]);
    await expectLater(plain.post('/v1/auth/login', body: {}, auth: false), throwsA(isA<OfflineException>()));
    expect(plainAdapter.requests, hasLength(1));

    final (keyed, keyedAdapter) = make([
      DioExceptionType.receiveTimeout,
      ScriptedAdapter.json(201, {'id': 'WD-1'}),
    ]);
    await keyed.post('/v1/withdrawals', body: {'amount_paise': 20000}, idempotencyKey: 'key-123-abc');
    expect(keyedAdapter.requests, hasLength(2));
    // The retry carries the same key, so the server does the work once.
    expect(keyedAdapter.requests.map((r) => r.headers['Idempotency-Key']), ['key-123-abc', 'key-123-abc']);
  }, timeout: const Timeout(Duration(seconds: 10)));

  test('server errors become typed exceptions with safe messages', () async {
    final (client, _) = make([
      ScriptedAdapter.json(400, {
        'error': {
          'code': 'VALIDATION_FAILED',
          'message': 'Please check the highlighted fields.',
          'fields': {'phone': 'Enter a 10-digit Indian mobile number.'},
        },
      }),
    ]);
    await expectLater(
      client.post('/v1/auth/signup', body: {}, auth: false),
      throwsA(isA<ServerRejection>().having((e) => e.fields['phone'], 'phone error', contains('10-digit'))),
    );
  });

  test('maintenance and upgrade have their own exceptions', () async {
    final (client, _) = make([
      ScriptedAdapter.json(503, {
        'error': {'code': 'MAINTENANCE', 'message': 'Back at 6 pm', 'until': '2026-10-01T12:30:00Z'},
      }),
      ScriptedAdapter.json(426, {
        'error': {'code': 'UPGRADE_REQUIRED', 'message': 'Update', 'download_url': 'https://x.test/app.apk'},
      }),
    ]);
    await expectLater(
      client.get('/v1/captcha', auth: false),
      throwsA(isA<MaintenanceException>().having((e) => e.message, 'message', 'Back at 6 pm')),
    );
    await expectLater(
      client.get('/v1/captcha', auth: false),
      throwsA(isA<UpgradeRequiredException>().having((e) => e.downloadUrl, 'url', 'https://x.test/app.apk')),
    );
  });
}
