import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/models.dart';
import '../../core/formatters/dates.dart';
import '../../core/formatters/inr.dart';
import '../../core/providers.dart';
import '../../core/widgets/app_background.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/paged_list.dart';
import '../wallet/wallet_screen.dart';

class WithdrawalHistoryScreen extends ConsumerWidget {
  const WithdrawalHistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final api = ref.watch(apiProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Withdrawal history')),
      body: AppBackground(
        child: PagedList<Withdrawal>(
          load: (cursor) => api.withdrawals(cursor: cursor),
          emptyTitle: 'No withdrawals yet',
          emptyMessage: 'Your withdrawals and their status will show here.',
          itemBuilder: (w) => Padding(
            padding: const EdgeInsets.only(bottom: Space.m),
            child: GlassCard(
              padding: const EdgeInsets.all(Space.l),
              child: MergeSemantics(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(child: Text(formatPaise(w.amountPaise), style: AppType.title)),
                        WithdrawalStatusChip(w.status),
                      ],
                    ),
                    const SizedBox(height: Space.s),
                    Text('To ${w.bankAccountMasked} · requested ${formatIstDateTime(w.requestedAt)}', style: AppType.caption),
                    Text('Reference ${w.id}', style: AppType.caption),
                    if (w.status == WithdrawalStatus.paid && w.bankReference != null)
                      Text(
                        'Paid ${w.paidAt == null ? '' : formatIstDate(w.paidAt!)} · bank ref ${w.bankReference}',
                        style: AppType.caption.copyWith(color: AppColors.success),
                      ),
                    if (w.status == WithdrawalStatus.failed)
                      Text(
                        '${w.failureReason ?? 'The bank could not complete the payment.'} The amount is back in your wallet.',
                        style: AppType.caption.copyWith(color: AppColors.danger),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
