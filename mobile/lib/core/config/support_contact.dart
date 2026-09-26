import '../api/models.dart';

/// Where "Contact support" goes: the support page if the admin set one,
/// otherwise an email to the support address. Null when neither is set.
Uri? supportContact(PublicConfig cfg) {
  final url = cfg.supportUrl;
  if (url != null && url.isNotEmpty) return Uri.parse(url);
  final email = cfg.supportEmail;
  if (email != null && email.isNotEmpty) {
    return Uri(scheme: 'mailto', path: email, query: 'subject=${Uri.encodeComponent('${cfg.companyName} support')}');
  }
  return null;
}
