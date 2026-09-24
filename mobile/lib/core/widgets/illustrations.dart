import 'dart:math';

import 'package:flutter/material.dart';

import '../../app/theme/colors.dart';
import '../animations/motion.dart';

/// Code-drawn "3D" illustrations: a lit sphere, a tilted ring and a glow,
/// with a symbol on top. They keep the APK small and look consistent.
/// Designers can later swap any preset for a rendered image (docs/APP.md).
class Illustration3D extends StatefulWidget {
  const Illustration3D({
    super.key,
    required this.icon,
    this.size = 160,
    this.accent = AppColors.violet,
    this.sphere = const [AppColors.goldBright, AppColors.gold, AppColors.goldDeep],
    this.iconColor = AppColors.ink,
    this.float = true,
    this.semanticLabel,
  });

  final IconData icon;
  final double size;
  final Color accent;
  final List<Color> sphere;
  final Color iconColor;
  final bool float;
  final String? semanticLabel;

  @override
  State<Illustration3D> createState() => _Illustration3DState();
}

class _Illustration3DState extends State<Illustration3D> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: const Duration(seconds: 6));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (widget.float && !Motion.of(context).reduced) {
      if (!_controller.isAnimating) _controller.repeat();
    } else {
      _controller.stop();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final size = widget.size;
    final art = AnimatedBuilder(
      animation: _controller,
      builder: (context, child) => Transform.translate(
        offset: Offset(0, sin(_controller.value * 2 * pi) * size * 0.025),
        child: child,
      ),
      child: SizedBox.square(
        dimension: size,
        child: Stack(
          alignment: Alignment.center,
          children: [
            CustomPaint(size: Size.square(size), painter: _OrbPainter(widget.accent, widget.sphere)),
            Padding(
              padding: EdgeInsets.only(bottom: size * 0.04),
              child: Icon(widget.icon, size: size * 0.3, color: widget.iconColor),
            ),
            CustomPaint(size: Size.square(size), painter: _RingFrontPainter(widget.accent)),
          ],
        ),
      ),
    );
    return Semantics(
      label: widget.semanticLabel,
      excludeSemantics: widget.semanticLabel == null,
      image: widget.semanticLabel != null,
      child: ExcludeSemantics(child: art),
    );
  }
}

Rect _ringRect(Size size) =>
    Rect.fromCenter(center: Offset(size.width / 2, size.height * 0.58), width: size.width * 0.96, height: size.height * 0.3);

class _OrbPainter extends CustomPainter {
  _OrbPainter(this.accent, this.sphere);

  final Color accent;
  final List<Color> sphere;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final r = size.width * 0.3;

    // Ambient glow.
    canvas.drawCircle(
      center,
      size.width / 2,
      Paint()
        ..shader = RadialGradient(
          colors: [accent.withValues(alpha: 0.45), accent.withValues(alpha: 0)],
        ).createShader(Rect.fromCircle(center: center, radius: size.width / 2)),
    );

    // Back half of the ring, behind the sphere.
    canvas.save();
    canvas.clipRect(Rect.fromLTWH(0, 0, size.width, size.height * 0.58));
    canvas.drawOval(
      _ringRect(size),
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = size.width * 0.018
        ..color = accent.withValues(alpha: 0.55),
    );
    canvas.restore();

    // Contact shadow.
    canvas.drawOval(
      Rect.fromCenter(center: center.translate(0, r * 1.2), width: r * 1.6, height: r * 0.28),
      Paint()
        ..color = Colors.black.withValues(alpha: 0.35)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10),
    );

    // Lit sphere: highlight top-left, shade bottom-right.
    final sphereRect = Rect.fromCircle(center: center, radius: r);
    canvas.drawCircle(
      center,
      r,
      Paint()
        ..shader = RadialGradient(
          center: const Alignment(-0.45, -0.5),
          radius: 1.05,
          colors: [...sphere, const Color(0xFF3A2A12)],
          stops: const [0.0, 0.35, 0.75, 1.0],
        ).createShader(sphereRect),
    );
    // Specular highlight.
    canvas.drawOval(
      Rect.fromCenter(center: center.translate(-r * 0.35, -r * 0.45), width: r * 0.6, height: r * 0.34),
      Paint()
        ..color = Colors.white.withValues(alpha: 0.55)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6),
    );
    // Rim light from the accent colour.
    canvas.drawCircle(
      center,
      r,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..color = accent.withValues(alpha: 0.5),
    );
  }

  @override
  bool shouldRepaint(covariant _OrbPainter old) => old.accent != accent || old.sphere != sphere;
}

class _RingFrontPainter extends CustomPainter {
  _RingFrontPainter(this.accent);

  final Color accent;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.clipRect(Rect.fromLTWH(0, size.height * 0.58, size.width, size.height));
    final rect = _ringRect(size);
    canvas.drawOval(
      rect,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = size.width * 0.022
        ..shader = LinearGradient(
          colors: [accent, AppColors.goldBright, accent],
        ).createShader(rect),
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _RingFrontPainter old) => old.accent != accent;
}

/// Presets used across screens, matching the design prompts in CLAUDE.md §40.
abstract final class Illustrations {
  static Widget launch({double size = 200}) =>
      Illustration3D(icon: Icons.auto_awesome_rounded, size: size, semanticLabel: 'Launch celebration');
  static Widget shield({double size = 160}) => Illustration3D(
    icon: Icons.verified_user_rounded,
    size: size,
    accent: AppColors.telegram,
    semanticLabel: 'Secure verification',
  );
  static Widget success({double size = 180}) => Illustration3D(
    icon: Icons.check_rounded,
    size: size,
    accent: AppColors.success,
    semanticLabel: 'Success',
  );
  static Widget network({double size = 150}) =>
      Illustration3D(icon: Icons.hub_rounded, size: size, semanticLabel: 'Referral network');
  static Widget wallet({double size = 150}) => Illustration3D(
    icon: Icons.account_balance_wallet_rounded,
    size: size,
    accent: AppColors.electric,
    semanticLabel: 'Wallet',
  );
  static Widget vault({double size = 140}) => Illustration3D(
    icon: Icons.account_balance_rounded,
    size: size,
    accent: AppColors.electric,
    semanticLabel: 'Secure bank payout',
  );
  static Widget share({double size = 150}) =>
      Illustration3D(icon: Icons.phonelink_ring_rounded, size: size, semanticLabel: 'Share with friends');
  static Widget crowd({double size = 120}) =>
      Illustration3D(icon: Icons.groups_rounded, size: size, semanticLabel: 'Members');
  static Widget offline({double size = 150}) => Illustration3D(
    icon: Icons.wifi_off_rounded,
    size: size,
    accent: AppColors.electric,
    sphere: const [Color(0xFFC9C3E6), Color(0xFF9C95C2), Color(0xFF5E5780)],
    semanticLabel: 'No connection',
  );
  static Widget maintenance({double size = 150}) => Illustration3D(
    icon: Icons.construction_rounded,
    size: size,
    accent: AppColors.warning,
    semanticLabel: 'Maintenance',
  );
  static Widget avatar({double size = 96}) =>
      Illustration3D(icon: Icons.person_rounded, size: size, float: false, semanticLabel: 'Profile');
}
