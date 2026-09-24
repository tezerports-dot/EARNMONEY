import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/json.dart';
import '../api/models.dart';

/// Where the session tokens live. Only the tokens: no passwords, balances
/// or personal data are stored on the phone.
abstract interface class TokenStore {
  Future<Tokens?> read();
  Future<void> write(Tokens tokens);
  Future<void> clear();
}

/// Android Keystore-backed storage (flutter_secure_storage), cached in memory.
class SecureTokenStore implements TokenStore {
  SecureTokenStore([FlutterSecureStorage? storage]) : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'ff_session_v1';
  final FlutterSecureStorage _storage;
  Tokens? _cache;
  bool _loaded = false;

  @override
  Future<Tokens?> read() async {
    if (_loaded) return _cache;
    try {
      final raw = await _storage.read(key: _key);
      _cache = raw == null ? null : Tokens.fromJson(jsonDecode(raw) as Json);
    } on Object {
      // Unreadable (for example after a restore to a new phone): start signed out.
      _cache = null;
      await _storage.delete(key: _key);
    }
    _loaded = true;
    return _cache;
  }

  @override
  Future<void> write(Tokens tokens) async {
    _cache = tokens;
    _loaded = true;
    await _storage.write(key: _key, value: jsonEncode(tokens.toJson()));
  }

  @override
  Future<void> clear() async {
    _cache = null;
    _loaded = true;
    await _storage.delete(key: _key);
  }
}

/// For tests.
class MemoryTokenStore implements TokenStore {
  Tokens? tokens;

  @override
  Future<Tokens?> read() async => tokens;

  @override
  Future<void> write(Tokens value) async => tokens = value;

  @override
  Future<void> clear() async => tokens = null;
}
