import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/models.dart';
import '../../core/providers.dart';
import '../../core/widgets/app_background.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/paged_list.dart';
import 'referrals_screen.dart';

/// Level 1 only. Friends-of-friends are counts on the table, never names.
class DirectReferralsScreen extends ConsumerWidget {
  const DirectReferralsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final api = ref.watch(apiProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Direct referrals')),
      body: AppBackground(
        child: PagedList<DirectReferral>(
          load: (cursor) => api.directReferrals(cursor: cursor),
          header: [
            const Text(
              'Friends who signed up with your code. Phone numbers are masked for their privacy.',
              style: AppType.bodySmall,
            ),
            const SizedBox(height: Space.l),
          ],
          emptyTitle: 'No direct referrals yet',
          emptyMessage: 'When a friend signs up with your code, they appear here.',
          itemBuilder: (r) => Padding(
            padding: const EdgeInsets.only(bottom: Space.s),
            child: GlassCard(padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.s), child: DirectReferralTile(referral: r)),
          ),
        ),
      ),
    );
  }
}
