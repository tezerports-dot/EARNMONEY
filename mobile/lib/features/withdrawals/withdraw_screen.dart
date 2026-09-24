import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/api_exception.dart';
import '../../core/api/models.dart';
import '../../core/data_providers.dart';
import '../../core/formatters/dates.dart';
import '../../core/formatters/inr.dart';
import '../../core/providers.dart';
import '../../core/security/idempotency.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/figures.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/inputs.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';
import '../wallet/wallet_screen.dart';

enum _Step { enter, review, submitting, done }

/// Review → Confirm → Submitting → Success/Failure (CLAUDE.md §31).
/// "Success" only appears after the server has confirmed the request.
class WithdrawScreen extends ConsumerStatefulWidget {
  const WithdrawScreen({super.key});

  @override
  ConsumerState<WithdrawScreen> createState() => _WithdrawScreenState();
}

class _WithdrawScreenState extends ConsumerState<WithdrawScreen> {
  final _amount = TextEditingController();
  _Step _step = _Step.enter;
  int? _amountPaise;
  String? _amountError;
  String? _submitError;
  Withdrawal? _result;
  String? _idempotencyKey;
  bool _prefilled = false;

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  void _startReview(Wallet w) {
    final paise = parseRupeesToPaise(_amount.text);
    String? error;
    if (paise == null || paise <= 0) {
      error = 'Enter an amount in rupees, like 2,400.';
    } else if (paise < w.minWithdrawalPaise) {
      error = 'The minimum is ${formatPaise(w.minWithdrawalPaise)}.';
    } else if (paise > w.availablePaise) {
      error = 'You have ${formatPaise(w.availablePaise)} available.';
    }
    setState(() {
      _amountError = error;
      if (error == null) {
        _amountPaise = paise;
        _idempotencyKey = newIdempotencyKey(); // one key for this confirmed request
        _submitError = null;
        _step = _Step.review;
      }
    });
  }

  Future<void> _confirm() async {
    setState(() {
      _step = _Step.submitting;
      _submitError = null;
    });
    try {
      final result = await ref
          .read(apiProvider)
          .requestWithdrawal(amountPaise: _amountPaise!, idempotencyKey: _idempotencyKey!);
      ref
        ..invalidate(walletProvider)
        ..invalidate(bankDetailsProvider)
        ..invalidate(dashboardProvider);
      setState(() {
        _result = result;
        _step = _Step.done;
      });
    } on OfflineException catch (e) {
      // Same key on retry: the server processes it at most once.
      setState(() {
        _submitError = '${e.userMessage} Your request may not have been received. Tap Confirm again to retry safely.';
        _step = _Step.review;
      });
    } on ApiException catch (e) {
      setState(() {
        _submitError = e.userMessage;
        _step = _Step.review;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final wallet = ref.watch(walletProvider);
    final bank = ref.watch(bankDetailsProvider);
    return PopScope(
      canPop: _step != _Step.submitting,
      child: AppScreen(
        title: 'Withdraw',
        children: [
          AsyncBody<Wallet>(
            value: wallet,
            onRetry: () => ref.invalidate(walletProvider),
            data: (w) => AsyncBody<BankDetails>(
              value: bank,
              onRetry: () => ref.invalidate(bankDetailsProvider),
              data: (b) => switch (_step) {
                _Step.done => _Done(result: _result!),
                _ when !w.payoutsOpen => EmptyView(
                  icon: Icons.event_rounded,
                  title: 'Withdrawals aren’t open yet',
                  message: 'You can withdraw from ${formatIstDate(w.payoutOpensAt)}.',
                ),
                _ when !b.saved => EmptyView(
                  icon: Icons.account_balance_outlined,
                  title: 'Add your bank details first',
                  message: 'We pay withdrawals only to a bank account in your name.',
                  action: PrimaryButton(label: 'Add bank details', onPressed: () => context.push('/wallet/bank')),
                ),
                _Step.enter => _enterView(w, b),
                _Step.review || _Step.submitting => _reviewView(w, b),
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _enterView(Wallet w, BankDetails b) {
    if (!_prefilled) {
      _prefilled = true;
      _amount.text = groupIndian(w.availablePaise ~/ 100);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Center(child: Illustrations.vault()),
        const SizedBox(height: Space.l),
        GlassCard(
          highlight: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Available to withdraw', style: AppType.caption),
              Amount(w.availablePaise, style: AppType.figure),
            ],
          ),
        ),
        const SizedBox(height: Space.l),
        _BankCard(bank: b),
        const SizedBox(height: Space.l),
        AppTextField(
          controller: _amount,
          label: 'Amount (₹)',
          prefixIcon: Icons.currency_rupee_rounded,
          errorText: _amountError,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))],
          helper: 'Minimum ${formatPaise(w.minWithdrawalPaise)}.',
        ),
        const SizedBox(height: Space.l),
        const _ProcessingInfo(),
        const SizedBox(height: Space.xl),
        PrimaryButton(label: 'Review withdrawal', onPressed: () => _startReview(w)),
      ],
    );
  }

  Widget _reviewView(Wallet w, BankDetails b) {
    final submitting = _step == _Step.submitting;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text('Review and confirm', style: AppType.title),
        const SizedBox(height: Space.l),
        GlassCard(
          child: Column(
            children: [
              _ReviewRow('Amount', formatPaise(_amountPaise!)),
              const Divider(height: Space.xl),
              _ReviewRow('To', '${b.accountHolderName}\n${b.accountNumberMasked} · ${b.ifsc}'),
              const Divider(height: Space.xl),
              _ReviewRow('Left in wallet', formatPaise(w.availablePaise - _amountPaise!)),
            ],
          ),
        ),
        if (_submitError != null) ...[
          const SizedBox(height: Space.l),
          Semantics(
            liveRegion: true,
            child: Text(_submitError!, style: AppType.bodySmall.copyWith(color: AppColors.danger)),
          ),
        ],
        const SizedBox(height: Space.xl),
        PrimaryButton(label: 'Confirm withdrawal', loading: submitting, onPressed: _confirm),
        const SizedBox(height: Space.m),
        SecondaryButton(
          label: 'Change amount',
          onPressed: submitting ? null : () => setState(() => _step = _Step.enter),
        ),
      ],
    );
  }
}

class _Done extends StatelessWidget {
  const _Done({required this.result});

  final Withdrawal result;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const SizedBox(height: Space.xl),
      Center(child: Illustrations.success(size: 150)),
      const SizedBox(height: Space.xl),
      const Text('Withdrawal requested', style: AppType.headline, textAlign: TextAlign.center),
      const SizedBox(height: Space.m),
      Text(
        '${formatPaise(result.amountPaise)} is on its way to ${result.bankAccountMasked}. '
        'We’ll update its status in your history.',
        style: AppType.body,
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: Space.xl),
      GlassCard(
        child: Column(
          children: [
            _ReviewRow('Reference', result.id),
            const Divider(height: Space.xl),
            Row(
              children: [
                const Expanded(child: Text('Status', style: AppType.bodySmall)),
                WithdrawalStatusChip(result.status),
              ],
            ),
          ],
        ),
      ),
      const SizedBox(height: Space.xl),
      PrimaryButton(label: 'See withdrawal history', onPressed: () => context.pushReplacement('/wallet/history')),
      const SizedBox(height: Space.m),
      SecondaryButton(label: 'Back to wallet', onPressed: () => context.pop()),
    ],
  );
}

class _BankCard extends StatelessWidget {
  const _BankCard({required this.bank});

  final BankDetails bank;

  @override
  Widget build(BuildContext context) => GlassCard(
    onTap: bank.locked ? null : () => context.push('/wallet/bank'),
    child: Row(
      children: [
        const Icon(Icons.account_balance_rounded, color: AppColors.gold),
        const SizedBox(width: Space.m),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(bank.accountHolderName ?? '', style: AppType.label),
              Text('${bank.accountNumberMasked} · ${bank.ifsc}', style: AppType.caption),
            ],
          ),
        ),
        if (!bank.locked) Text('Change', style: AppType.caption.copyWith(color: AppColors.goldBright)),
      ],
    ),
  );
}

class _ProcessingInfo extends StatelessWidget {
  const _ProcessingInfo();

  @override
  Widget build(BuildContext context) => const GlassCard(
    padding: EdgeInsets.all(Space.l),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(Icons.schedule_rounded, color: AppColors.textSecondary),
        SizedBox(width: Space.m),
        Expanded(
          child: Text(
            'Withdrawals are paid by bank transfer in batches. Your history shows each step: '
            'Requested, Processing, then Paid with the bank reference. If a payment fails, '
            'the money returns to your wallet.',
            style: AppType.bodySmall,
          ),
        ),
      ],
    ),
  );
}

class _ReviewRow extends StatelessWidget {
  const _ReviewRow(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => MergeSemantics(
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: Text(label, style: AppType.bodySmall)),
        Flexible(
          child: Text(value, style: AppType.label, textAlign: TextAlign.right),
        ),
      ],
    ),
  );
}
