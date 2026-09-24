import 'package:flutter/material.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../animations/motion.dart';
import '../formatters/inr.dart';

/// Counts up to [value] (a real number from the server) with Indian grouping.
/// The animation only moves between real values; it never invents one.
class AnimatedCount extends StatelessWidget {
  const AnimatedCount({super.key, required this.value, this.style, this.money = false, this.semanticsLabel});

  final int value;
  final TextStyle? style;

  /// Treat [value] as paise and show rupees.
  final bool money;
  final String? semanticsLabel;

  String _format(int v) => money ? formatPaise(v) : groupIndian(v);

  @override
  Widget build(BuildContext context) {
    final motion = Motion.of(context);
    final text = Semantics(
      label: semanticsLabel == null ? _format(value) : '$semanticsLabel: ${_format(value)}',
      excludeSemantics: true,
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: value.toDouble()),
        duration: motion.counter,
        curve: Motion.curve,
        // Drawing an intermediate frame is the only place a double appears;
        // the final frame is always exactly [value].
        builder: (context, t, _) => Text(
          _format(t >= value ? value : (money ? (t ~/ 100) * 100 : t.round())),
          style: style ?? AppType.figure,
          maxLines: 1,
          overflow: TextOverflow.fade,
          softWrap: false,
        ),
      ),
    );
    return text;
  }
}

class Amount extends StatelessWidget {
  const Amount(this.paise, {super.key, this.style});

  final int paise;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) =>
      Text(formatPaise(paise), style: style ?? AppType.title.copyWith(fontFeatures: const [FontFeature.tabularFigures()]));
}

/// Animated progress toward a goal, with the percentage in words too.
class GoalProgress extends StatelessWidget {
  const GoalProgress({super.key, required this.value, required this.goal, this.label});

  final int value;
  final int goal;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final motion = Motion.of(context);
    final fraction = goal <= 0 ? 0.0 : (value / goal).clamp(0.0, 1.0);
    // Percent with one decimal, computed on integers (basis points).
    final basisPoints = goal <= 0 ? 0 : (value * 10000 ~/ goal).clamp(0, 10000);
    final percent = '${basisPoints ~/ 100}.${(basisPoints % 100 ~/ 10)}%';
    return Semantics(
      label: '${label ?? 'Progress'}: $percent',
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: SizedBox(
              height: 12,
              child: Stack(
                children: [
                  Container(color: Colors.white.withValues(alpha: 0.08)),
                  TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0, end: fraction),
                    duration: motion.counter,
                    curve: Motion.curve,
                    builder: (context, t, _) => FractionallySizedBox(
                      widthFactor: t == 0 ? 0 : t.clamp(0.012, 1.0),
                      child: const DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(colors: [AppColors.violet, AppColors.gold]),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: Space.s),
          Text(percent, style: AppType.caption.copyWith(color: AppColors.textSecondary)),
        ],
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.trailing});

  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: Space.xxl, bottom: Space.m),
    child: Row(
      children: [
        Expanded(child: Semantics(header: true, child: Text(text, style: AppType.title))),
        ?trailing,
      ],
    ),
  );
}
