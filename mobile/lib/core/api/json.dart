typedef Json = Map<String, Object?>;

/// Strict readers: a response that doesn't match docs/API.md fails loudly
/// with a [FormatException] instead of turning into a wrong number on screen.
extension JsonRead on Json {
  String str(String key) {
    final value = this[key];
    if (value is String) return value;
    throw FormatException('Expected text at "$key"');
  }

  String? strOrNull(String key) {
    final value = this[key];
    if (value == null || value is String) return value as String?;
    throw FormatException('Expected text or null at "$key"');
  }

  int integer(String key) {
    final value = this[key];
    if (value is int) return value;
    throw FormatException('Expected a whole number at "$key"');
  }

  int? integerOrNull(String key) {
    final value = this[key];
    if (value == null || value is int) return value as int?;
    throw FormatException('Expected a whole number or null at "$key"');
  }

  bool boolean(String key) {
    final value = this[key];
    if (value is bool) return value;
    throw FormatException('Expected true/false at "$key"');
  }

  DateTime time(String key) => DateTime.parse(str(key)).toUtc();

  DateTime? timeOrNull(String key) {
    final value = strOrNull(key);
    return value == null ? null : DateTime.parse(value).toUtc();
  }

  Json obj(String key) {
    final value = this[key];
    if (value is Map<String, Object?>) return value;
    throw FormatException('Expected an object at "$key"');
  }

  Json? objOrNull(String key) {
    final value = this[key];
    if (value == null) return null;
    if (value is Map<String, Object?>) return value;
    throw FormatException('Expected an object or null at "$key"');
  }

  List<Json> list(String key) {
    final value = this[key];
    if (value is List<Object?>) {
      return value.map((item) {
        if (item is Map<String, Object?>) return item;
        throw FormatException('Expected objects in "$key"');
      }).toList();
    }
    throw FormatException('Expected a list at "$key"');
  }
}
