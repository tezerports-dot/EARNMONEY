import 'dart:math';

import 'package:flutter/material.dart';

import '../../app/theme/colors.dart';
import '../animations/motion.dart';

/// A short, one-time burst of confetti for success and launch moments.
/// Skipped entirely when the phone asks for reduced motion.
class ConfettiBurst extends StatefulWidget {
  const ConfettiBurst({super.key, this.pieces = 60});

  final int pieces;

  @override
  State<ConfettiBurst> createState() => _ConfettiBurstState();
}

class _ConfettiBurstState extends State<ConfettiBurst> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2600),
  );
  late final List<_Piece> _pieces = List.generate(widget.pieces, (i) => _Piece(Random(i * 7 + 3)));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!Motion.of(context).reduced && !_controller.isAnimating && _controller.value == 0) _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (Motion.of(context).reduced) return const SizedBox.shrink();
    return IgnorePointer(
      child: CustomPaint(painter: _ConfettiPainter(_controller, _pieces), size: Size.infinite),
    );
  }
}

class _Piece {
  _Piece(Random r)
    : x = r.nextDouble(),
      drift = (r.nextDouble() - 0.5) * 0.4,
      speed = 0.6 + r.nextDouble() * 0.6,
      spin = r.nextDouble() * 6,
      delay = r.nextDouble() * 0.25,
      color = const [
        AppColors.gold,
        AppColors.goldBright,
        AppColors.violet,
        AppColors.electric,
        AppColors.success,
      ][r.nextInt(5)];

  final double x;
  final double drift;
  final double speed;
  final double spin;
  final double delay;
  final Color color;
}

class _ConfettiPainter extends CustomPainter {
  _ConfettiPainter(this.animation, this.pieces) : super(repaint: animation);

  final Animation<double> animation;
  final List<_Piece> pieces;

  @override
  void paint(Canvas canvas, Size size) {
    for (final p in pieces) {
      final t = ((animation.value - p.delay) / (1 - p.delay)).clamp(0.0, 1.0);
      if (t == 0) continue;
      final y = -20 + t * p.speed * (size.height + 40);
      final x = (p.x + p.drift * t) * size.width;
      final paint = Paint()..color = p.color.withValues(alpha: 1 - t * 0.6);
      canvas.save();
      canvas.translate(x, y);
      canvas.rotate(p.spin * t * pi);
      canvas.drawRRect(RRect.fromRectAndRadius(const Rect.fromLTWH(-4, -2, 8, 4), const Radius.circular(1)), paint);
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(covariant _ConfettiPainter oldDelegate) => false;
}
