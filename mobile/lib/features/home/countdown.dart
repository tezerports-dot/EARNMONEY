import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/config/config_controller.dart';
import '../../core/formatters/dates.dart';
import '../../core/widgets/glass_card.dart';

/// Counts down to [target] using the server's clock. When it reaches zero it
/// reloads the configuration once, so the screen switches to the next state
/// instead of showing an expired promotion (CLAUDE.md §34).
class CountdownCard extends ConsumerStatefulWidget {
  const CountdownCard({super.key, required this.target, required this.title, required this.doneText});

  final DateTime target;
  final String title;
  final String doneText;

  @override
  ConsumerState<CountdownCard> createState() => _CountdownCardState();
}

class _CountdownCardState extends ConsumerState<CountdownCard> {
  Timer? _timer;
  bool _reloaded = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
  }

  void _tick() {
    if (!mounted) return;
    final now = ref.read(configProvider).value?.serverNow() ?? DateTime.now().toUtc();
    if (!now.isBefore(widget.target) && !_reloaded) {
      _reloaded = true;
      ref.read(configProvider.notifier).reload();
    }
    setState(() {});
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final now = ref.watch(configProvider).value?.serverNow() ?? DateTime.now().toUtc();
    final parts = CountdownParts.from(widget.target.difference(now));
    final label = parts.isZero
        ? widget.doneText
        : '${widget.title}: ${parts.days} days, ${parts.hours} hours, ${parts.minutes} minutes';
    return GlassCard(
      highlight: true,
      semanticLabel: label,
      child: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.title.toUpperCase(),
              style: AppType.caption.copyWith(color: AppColors.goldBright, letterSpacing: 1.2),
            ),
            const SizedBox(height: Space.m),
            if (parts.isZero)
              Text(widget.doneText, style: AppType.headline)
            else
              Row(
                children: [
                  _Unit(parts.days, 'days'),
                  _Unit(parts.hours, 'hrs'),
                  _Unit(parts.minutes, 'min'),
                  _Unit(parts.seconds, 'sec'),
                ],
              ),
            const SizedBox(height: Space.m),
            Text(formatIstDateTime(widget.target), style: AppType.caption),
          ],
        ),
      ),
    );
  }
}

class _Unit extends StatelessWidget {
  const _Unit(this.value, this.label);

  final int value;
  final String label;

  @override
  Widget build(BuildContext context) => Expanded(
    child: Column(
      children: [
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(value.toString().padLeft(2, '0'), style: AppType.figure.copyWith(fontSize: 30)),
        ),
        Text(label, style: AppType.caption),
      ],
    ),
  );
}
