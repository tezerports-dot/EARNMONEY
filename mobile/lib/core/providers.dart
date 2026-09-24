import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api/future_fashion_api.dart';
import 'auth/token_store.dart';
import 'storage/prefs.dart';

/// Overridden in main.dart (real services) and in tests (fakes).
final apiProvider = Provider<FutureFashionApi>((ref) => throw UnimplementedError('apiProvider not overridden'));
final tokenStoreProvider = Provider<TokenStore>((ref) => throw UnimplementedError('tokenStoreProvider not overridden'));
final prefsProvider = Provider<AppPrefs>((ref) => throw UnimplementedError('prefsProvider not overridden'));
final appVersionProvider = Provider<String>((ref) => '1.0.0');
