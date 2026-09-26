import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/models.dart';
import '../../core/data_providers.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';

class RecruitmentScreen extends ConsumerWidget {
  const RecruitmentScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final posts = ref.watch(recruitmentProvider);
    return AppScreen(
      title: 'Jobs',
      onRefresh: () async {
        ref.invalidate(recruitmentProvider);
        await ref.read(recruitmentProvider.future);
      },
      children: [
        const SizedBox(height: Space.m),
        AsyncBody<List<RecruitmentPost>>(
          value: posts,
          onRetry: () => ref.invalidate(recruitmentProvider),
          data: (items) => items.isEmpty
              ? const EmptyView(title: 'No openings right now', message: 'Check back soon.')
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final post in items) ...[_PostCard(post: post), const SizedBox(height: Space.m)],
                  ],
                ),
        ),
      ],
    );
  }
}

class _PostCard extends StatelessWidget {
  const _PostCard({required this.post});

  final RecruitmentPost post;

  @override
  Widget build(BuildContext context) {
    final details = [post.location, post.employmentType]
        .whereType<String>()
        .where((text) => text.isNotEmpty)
        .join(' • ');
    final applyUri = post.applyUrl == null
        ? (post.applyEmail == null ? null : Uri.parse('mailto:${post.applyEmail}'))
        : Uri.parse(post.applyUrl!);
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(post.title, style: AppType.title),
          if (details.isNotEmpty) ...[
            const SizedBox(height: Space.xs),
            Text(details, style: AppType.caption.copyWith(color: AppColors.textMuted)),
          ],
          const SizedBox(height: Space.m),
          Text(post.description, style: AppType.body),
          if (applyUri != null) ...[
            const SizedBox(height: Space.l),
            PrimaryButton(
              label: 'Apply',
              onPressed: () => unawaited(launchUrl(applyUri, mode: LaunchMode.externalApplication)),
            ),
          ],
        ],
      ),
    );
  }
}
