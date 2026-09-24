import 'package:intl/intl.dart';

/// Campaign times are shown in India Standard Time whatever the phone's zone.
const Duration istOffset = Duration(hours: 5, minutes: 30);

DateTime toIst(DateTime utc) => utc.toUtc().add(istOffset);

String formatIstDate(DateTime utc) => DateFormat('d MMMM y').format(toIst(utc));

String formatIstDayMonth(DateTime utc) => DateFormat('d MMMM').format(toIst(utc));

String formatIstDateTime(DateTime utc) => '${DateFormat('d MMM y, h:mm a').format(toIst(utc))} IST';

/// Parts of a countdown, clamped at zero.
class CountdownParts {
  const CountdownParts(this.days, this.hours, this.minutes, this.seconds);

  factory CountdownParts.from(Duration remaining) {
    final total = remaining.isNegative ? 0 : remaining.inSeconds;
    return CountdownParts(total ~/ 86400, (total % 86400) ~/ 3600, (total % 3600) ~/ 60, total % 60);
  }

  final int days;
  final int hours;
  final int minutes;
  final int seconds;

  bool get isZero => days == 0 && hours == 0 && minutes == 0 && seconds == 0;
}
