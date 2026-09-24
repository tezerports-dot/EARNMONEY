/// Every failure the API layer reports. Screens show [userMessage]; they
/// never show raw server errors, codes or stack traces.
sealed class ApiException implements Exception {
  const ApiException();

  String get userMessage;
}

/// No connection, a timeout, or the server couldn't be reached.
final class OfflineException extends ApiException {
  const OfflineException();

  @override
  String get userMessage => 'You seem to be offline. Check your connection and try again.';
}

final class MaintenanceException extends ApiException {
  const MaintenanceException(this.message, this.until);

  final String? message;
  final DateTime? until;

  @override
  String get userMessage => message ?? "We're doing some maintenance. Please try again soon.";
}

final class UpgradeRequiredException extends ApiException {
  const UpgradeRequiredException(this.downloadUrl);

  final String? downloadUrl;

  @override
  String get userMessage => 'Please update the app to continue.';
}

/// The login ended (expired, revoked, or used elsewhere). The app signs out.
final class SessionEndedException extends ApiException {
  const SessionEndedException();

  @override
  String get userMessage => 'Your session has ended. Please log in again.';
}

/// An error the server explained: validation, business rules, rate limits.
final class ServerRejection extends ApiException {
  const ServerRejection({
    required this.status,
    required this.code,
    required this.message,
    this.fields = const {},
    this.retryAfter,
  });

  final int status;
  final String code;
  final String message;
  final Map<String, String> fields;
  final Duration? retryAfter;

  bool get isRetryableServerError => status == 502 || status == 503 || status == 504;

  @override
  String get userMessage => message;
}

/// Anything unexpected (a malformed response, an unknown failure).
final class UnexpectedException extends ApiException {
  const UnexpectedException();

  @override
  String get userMessage => 'Something went wrong. Please try again.';
}
