import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../api/api_exception.dart';
import 'buttons.dart';
import 'glass_card.dart';

/// Placeholder blocks while data loads, so a screen is never blank.
class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.blocks = 3});

  final int blocks;

  @override
  Widget build(BuildContext context) => Semantics(
    label: 'Loading',
    liveRegion: true,
    child: Column(
      children: [
        for (var i = 0; i < blocks; i++) ...[
          Container(
            height: i == 0 ? 140 : 88,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.05),
              borderRadius: BorderRadius.circular(Radii.card),
            ),
          ),
          const SizedBox(height: Space.l),
        ],
      ],
    ),
  );
}

class EmptyView extends StatelessWidget {
  const EmptyView({
    super.key,
    required this.title,
    required this.message,
    this.icon = Icons.inbox_outlined,
    this.action,
  });

  final String title;
  final String message;
  final IconData icon;
  final Widget? action;

  @override
  Widget build(BuildContext context) => GlassCard(
    child: Column(
      children: [
        Icon(icon, size: 40, color: AppColors.textMuted),
        const SizedBox(height: Space.m),
        Text(title, style: AppType.title, textAlign: TextAlign.center),
        const SizedBox(height: Space.s),
        Text(message, style: AppType.bodySmall, textAlign: TextAlign.center),
        if (action != null) ...[const SizedBox(height: Space.l), action!],
      ],
    ),
  );
}

/// A failed load with a way to retry. Offline gets its own wording.
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final offline = error is OfflineException;
    final message = error is ApiException
        ? (error as ApiException).userMessage
        : const UnexpectedException().userMessage;
    return GlassCard(
      child: Column(
        children: [
          Icon(offline ? Icons.wifi_off_rounded : Icons.error_outline_rounded, size: 40, color: AppColors.warning),
          const SizedBox(height: Space.m),
          Text(
            offline ? 'Connection unavailable' : "Couldn't load this",
            style: AppType.title,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: Space.s),
          Text(message, style: AppType.bodySmall, textAlign: TextAlign.center),
          const SizedBox(height: Space.l),
          SecondaryButton(label: 'Try again', icon: Icons.refresh_rounded, onPressed: onRetry),
        ],
      ),
    );
  }
}

/// Shows loading, error or data for an [AsyncValue], keeping old data on
/// screen while it refreshes.
class AsyncBody<T> extends StatelessWidget {
  const AsyncBody({super.key, required this.value, required this.onRetry, required this.data, this.loadingBlocks = 3});

  final AsyncValue<T> value;
  final VoidCallback onRetry;
  final Widget Function(T data) data;
  final int loadingBlocks;

  @override
  Widget build(BuildContext context) => value.when(
    data: data,
    loading: () => LoadingView(blocks: loadingBlocks),
    error: (error, _) => ErrorView(error: error, onRetry: onRetry),
  );
}

void showMessage(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));
}

String errorMessage(Object error) =>
    error is ApiException ? error.userMessage : const UnexpectedException().userMessage;
