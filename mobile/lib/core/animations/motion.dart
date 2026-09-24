import 'package:flutter/widgets.dart';

/// Motion tokens (docs/APP.md). When the phone asks for reduced motion,
/// every duration becomes zero and decorative loops stop.
class Motion {
  const Motion._(this.reduced);

  factory Motion.of(BuildContext context) => Motion._(MediaQuery.maybeDisableAnimationsOf(context) ?? false);

  final bool reduced;

  Duration get tap => reduced ? Duration.zero : const Duration(milliseconds: 150);
  Duration get transition => reduced ? Duration.zero : const Duration(milliseconds: 250);
  Duration get entrance => reduced ? Duration.zero : const Duration(milliseconds: 400);
  Duration get counter => reduced ? Duration.zero : const Duration(milliseconds: 1200);

  static const Curve curve = Curves.easeOutCubic;
}

/// Fades and lifts its child in once. Doesn't block taps while animating.
class EntranceFade extends StatelessWidget {
  const EntranceFade({super.key, required this.child, this.delay = Duration.zero});

  final Widget child;
  final Duration delay;

  @override
  Widget build(BuildContext context) {
    final motion = Motion.of(context);
    if (motion.reduced) return child;
    final total = motion.entrance + delay;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: total,
      curve: Interval(delay.inMilliseconds / total.inMilliseconds, 1, curve: Motion.curve),
      builder: (context, t, child) => Opacity(
        opacity: t,
        child: Transform.translate(offset: Offset(0, (1 - t) * 16), child: child),
      ),
      child: child,
    );
  }
}
