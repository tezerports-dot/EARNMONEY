import 'dart:async';

import 'package:app_links/app_links.dart';

import '../../app/env.dart';
import '../storage/prefs.dart';

/// Letters and digits used in referral codes (no 0/O, 1/I/L or U).
const _codeAlphabet = '23456789ABCDEFGHJKMNPQRSTVWXYZ';

/// Normalises what a user pastes or a link carries; null if it can't be a code.
String? normalizeReferralCode(String? raw) {
  if (raw == null) return null;
  final code = raw.replaceAll(RegExp(r'\s'), '').toUpperCase();
  if (code.length != 8 || code.split('').any((c) => !_codeAlphabet.contains(c))) return null;
  return code;
}

/// Extracts the code from `https://<host>/r/CODE` or `futurefashion://r/CODE`.
String? referralCodeFromUri(Uri uri) {
  final isWeb = uri.scheme == 'https' && uri.host == AppEnv.webHost;
  final isCustom = uri.scheme == 'futurefashion' && uri.host == 'r';
  if (isWeb && uri.pathSegments.length >= 2 && uri.pathSegments.first == 'r') {
    return normalizeReferralCode(uri.pathSegments[1]);
  }
  if (isCustom && uri.pathSegments.isNotEmpty) return normalizeReferralCode(uri.pathSegments.first);
  return null;
}

/// Remembers a referral code from an opened link so signup can pre-fill it
/// (case 29: link before install is handled by the landing page's copy
/// button; case 30: link after install arrives here).
class ReferralLinkListener {
  ReferralLinkListener(this._prefs, {AppLinks? links}) : _links = links ?? AppLinks();

  final AppPrefs _prefs;
  final AppLinks _links;
  StreamSubscription<Uri>? _subscription;

  Future<void> start() async {
    try {
      final initial = await _links.getInitialLink();
      if (initial != null) await _remember(initial);
    } on Object {
      // No launch link, or the platform can't provide it.
    }
    _subscription = _links.uriLinkStream.listen(_remember, onError: (Object _) {});
  }

  Future<void> _remember(Uri uri) async {
    final code = referralCodeFromUri(uri);
    if (code != null) await _prefs.setPendingReferralCode(code);
  }

  Future<void> stop() async => _subscription?.cancel();
}
