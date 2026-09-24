import 'package:flutter/material.dart';

import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import 'app_background.dart';

/// Standard screen: glowing background, safe area, optional title and
/// pull-to-refresh, scrollable content with the design system's padding.
class AppScreen extends StatelessWidget {
  const AppScreen({
    super.key,
    required this.children,
    this.title,
    this.onRefresh,
    this.particles = false,
    this.bottom,
    this.actions,
    this.showBack,
  });

  final List<Widget> children;
  final String? title;
  final Future<void> Function()? onRefresh;
  final bool particles;

  /// Pinned under the scrolling content (for example a primary button).
  final Widget? bottom;
  final List<Widget>? actions;
  final bool? showBack;

  @override
  Widget build(BuildContext context) {
    final canPop = showBack ?? Navigator.of(context).canPop();
    final list = ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(Space.screen, Space.s, Space.screen, Space.xxxl),
      children: children,
    );
    return Scaffold(
      backgroundColor: Colors.transparent,
      extendBodyBehindAppBar: false,
      appBar: title == null && !canPop && actions == null
          ? null
          : AppBar(
              automaticallyImplyLeading: canPop,
              title: title == null ? null : Semantics(header: true, child: Text(title!, style: AppType.title)),
              actions: actions,
            ),
      body: AppBackground(
        particles: particles,
        child: SafeArea(
          top: title == null && !canPop,
          child: Column(
            children: [
              Expanded(child: onRefresh == null ? list : RefreshIndicator(onRefresh: onRefresh!, child: list)),
              if (bottom != null)
                Padding(padding: const EdgeInsets.fromLTRB(Space.screen, Space.s, Space.screen, Space.l), child: bottom),
            ],
          ),
        ),
      ),
    );
  }
}
