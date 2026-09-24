import 'dart:math';

import 'package:flutter/material.dart';

import '../../app/theme/colors.dart';
import '../animations/motion.dart';

/// The layered, glowing backdrop behind every screen.
class AppBackground extends StatelessWidget {
  const AppBackground({super.key, required this.child, this.particles = false});

  final Widget child;

  /// Slow floating specks for celebratory screens. Off with reduced motion.
  final bool particles;

  @override
  Widget build(BuildContext context) {
    final motion = Motion.of(context);
    return DecoratedBox(
      decoration: const BoxDecoration(gradient: AppColors.backgroundGradient),
      child: Stack(
        fit: StackFit.expand,
        children: [
          const IgnorePointer(child: CustomPaint(painter: _GlowPainter())),
          if (particles && !motion.reduced) const IgnorePointer(child: _Particles()),
          child,
        ],
      ),
    );
  }
}

class _GlowPainter extends CustomPainter {
  const _GlowPainter();

  @override
  void paint(Canvas canvas, Size size) {
    void glow(Offset center, double radius, Color color) {
      canvas.drawCircle(
        center,
        radius,
        Paint()
          ..shader = RadialGradient(colors: [color, color.withValues(alpha: 0)])
              .createShader(Rect.fromCircle(center: center, radius: radius)),
      );
    }

    glow(Offset(size.width * 0.85, size.height * 0.08), size.width * 0.7, AppColors.violet.withValues(alpha: 0.22));
    glow(Offset(size.width * 0.05, size.height * 0.35), size.width * 0.6, AppColors.gold.withValues(alpha: 0.08));
    glow(Offset(size.width * 0.6, size.height * 0.95), size.width * 0.8, AppColors.electric.withValues(alpha: 0.10));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _Particles extends StatefulWidget {
  const _Particles();

  @override
  State<_Particles> createState() => _ParticlesState();
}

class _ParticlesState extends State<_Particles> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: const Duration(seconds: 24))
    ..repeat();
  final List<_Speck> _specks = List.generate(22, (i) => _Speck(Random(i)));

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => CustomPaint(painter: _SpeckPainter(_controller, _specks));
}

class _Speck {
  _Speck(Random r) : x = r.nextDouble(), y = r.nextDouble(), size = 1 + r.nextDouble() * 2, phase = r.nextDouble();

  final double x;
  final double y;
  final double size;
  final double phase;
}

class _SpeckPainter extends CustomPainter {
  _SpeckPainter(this.animation, this.specks) : super(repaint: animation);

  final Animation<double> animation;
  final List<_Speck> specks;

  @override
  void paint(Canvas canvas, Size size) {
    for (final s in specks) {
      final t = (animation.value + s.phase) % 1;
      final dy = (s.y - t * 0.35) % 1;
      final alpha = 0.15 + 0.35 * sin(t * pi);
      canvas.drawCircle(
        Offset(s.x * size.width, dy * size.height),
        s.size,
        Paint()..color = AppColors.goldBright.withValues(alpha: alpha),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _SpeckPainter oldDelegate) => false;
}
