/// Money arrives from the server as integer paise. Formatting uses integer
/// arithmetic only, never `double`, so no amount is ever rounded wrongly.
String formatPaise(int paise) {
  final negative = paise < 0;
  final abs = negative ? -paise : paise;
  final rupees = abs ~/ 100;
  final rest = abs % 100;
  final grouped = groupIndian(rupees);
  final decimals = rest == 0 ? '' : '.${rest.toString().padLeft(2, '0')}';
  return '${negative ? '-' : ''}₹$grouped$decimals';
}

/// Indian digit grouping: 11577956 → 1,15,77,956.
String groupIndian(int value) {
  final negative = value < 0;
  final digits = (negative ? -value : value).toString();
  if (digits.length <= 3) return '${negative ? '-' : ''}$digits';
  final tail = digits.substring(digits.length - 3);
  var head = digits.substring(0, digits.length - 3);
  final groups = <String>[];
  while (head.length > 2) {
    groups.insert(0, head.substring(head.length - 2));
    head = head.substring(0, head.length - 2);
  }
  if (head.isNotEmpty) groups.insert(0, head);
  return '${negative ? '-' : ''}${groups.join(',')},$tail';
}

/// Parses what a user types in an amount field ("2,400" or "2400.50") into
/// paise. Returns null when it isn't a valid amount. The server re-checks.
int? parseRupeesToPaise(String input) {
  final cleaned = input.replaceAll(',', '').replaceAll('₹', '').trim();
  final match = RegExp(r'^(\d{1,11})(?:\.(\d{1,2}))?$').firstMatch(cleaned);
  if (match == null) return null;
  final rupees = int.parse(match.group(1)!);
  final fraction = match.group(2);
  final paise = fraction == null ? 0 : int.parse(fraction.padRight(2, '0'));
  return rupees * 100 + paise;
}
