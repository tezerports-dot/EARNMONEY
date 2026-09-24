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
import '../../core/providers.dart';
import '../../core/security/idempotency.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/inputs.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';

/// Bank account for payouts. The full number is sent once over HTTPS and
/// stored encrypted by the server; the app only ever shows the last 4 digits.
class BankDetailsScreen extends ConsumerStatefulWidget {
  const BankDetailsScreen({super.key});

  @override
  ConsumerState<BankDetailsScreen> createState() => _BankDetailsScreenState();
}

class _BankDetailsScreenState extends ConsumerState<BankDetailsScreen> {
  final _name = TextEditingController();
  final _number = TextEditingController();
  final _confirm = TextEditingController();
  final _ifsc = TextEditingController();
  final Map<String, String?> _errors = {};
  String? _formError;
  bool _busy = false;
  bool _editing = false;
  String? _key;
  String? _keyFor;

  @override
  void dispose() {
    _name.dispose();
    _number.dispose();
    _confirm.dispose();
    _ifsc.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    FocusScope.of(context).unfocus();
    final name = _name.text.trim();
    final number = _number.text.replaceAll(' ', '');
    final ifsc = _ifsc.text.trim().toUpperCase();
    setState(() {
      _errors
        ..clear()
        ..['account_holder_name'] = RegExp(r"^[A-Za-z][A-Za-z .'-]{1,99}$").hasMatch(name)
            ? null
            : 'Enter the name exactly as on the bank account.'
        ..['account_number'] = RegExp(r'^\d{9,18}$').hasMatch(number) ? null : 'Account numbers have 9 to 18 digits.'
        ..['confirm'] = _confirm.text.replaceAll(' ', '') == number ? null : 'The numbers don’t match.'
        ..['ifsc'] = RegExp(r'^[A-Z]{4}0[A-Z0-9]{6}$').hasMatch(ifsc)
            ? null
            : 'IFSC has 11 characters, like HDFC0001234.';
      _formError = null;
    });
    if (_errors.values.any((e) => e != null)) return;

    final signature = '$name|$number|$ifsc';
    if (_keyFor != signature) {
      _key = newIdempotencyKey();
      _keyFor = signature;
    }
    setState(() => _busy = true);
    try {
      await ref
          .read(apiProvider)
          .saveBankDetails(accountHolderName: name, accountNumber: number, ifsc: ifsc, idempotencyKey: _key!);
      ref.invalidate(bankDetailsProvider);
      _number.clear();
      _confirm.clear();
      if (!mounted) return;
      setState(() => _editing = false);
      showMessage(context, 'Bank details saved');
      if (context.canPop()) context.pop();
    } on ServerRejection catch (e) {
      setState(() {
        _errors.addAll(e.fields);
        _formError = e.fields.isEmpty ? e.message : null;
      });
    } on ApiException catch (e) {
      setState(() => _formError = e.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bank = ref.watch(bankDetailsProvider);
    return AppScreen(
      title: 'Bank details',
      children: [
        AsyncBody<BankDetails>(
          value: bank,
          onRetry: () => ref.invalidate(bankDetailsProvider),
          data: (b) => b.saved && !_editing ? _saved(b) : _form(b),
        ),
      ],
    );
  }

  Widget _saved(BankDetails b) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      GlassCard(
        highlight: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Payouts go to', style: AppType.caption),
            const SizedBox(height: Space.s),
            Text(b.accountHolderName!, style: AppType.title),
            const SizedBox(height: Space.xs),
            Text(b.accountNumberMasked!, style: AppType.body.copyWith(letterSpacing: 1.5)),
            Text('IFSC ${b.ifsc}', style: AppType.caption),
          ],
        ),
      ),
      const SizedBox(height: Space.l),
      if (b.locked)
        Text(
          'You can change these after your current withdrawal has been paid or has failed.',
          style: AppType.bodySmall.copyWith(color: AppColors.warning),
        )
      else
        SecondaryButton(
          label: 'Change bank details',
          onPressed: () {
            _name.text = b.accountHolderName ?? '';
            _ifsc.text = b.ifsc ?? '';
            setState(() => _editing = true);
          },
        ),
      const SizedBox(height: Space.l),
      const _PrivacyNote(),
    ],
  );

  Widget _form(BankDetails b) => AutofillGroup(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text('Add the bank account in your own name that should receive your rewards.', style: AppType.body),
        const SizedBox(height: Space.xl),
        AppTextField(
          controller: _name,
          label: 'Account holder name',
          errorText: _errors['account_holder_name'],
          prefixIcon: Icons.person_outline_rounded,
          textCapitalization: TextCapitalization.words,
          autofillHints: const [AutofillHints.name],
          maxLength: 100,
          textInputAction: TextInputAction.next,
        ),
        const FieldGap(),
        AppTextField(
          controller: _number,
          label: 'Account number',
          errorText: _errors['account_number'],
          prefixIcon: Icons.numbers_rounded,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(18)],
          textInputAction: TextInputAction.next,
        ),
        const FieldGap(),
        AppTextField(
          controller: _confirm,
          label: 'Confirm account number',
          errorText: _errors['confirm'],
          prefixIcon: Icons.numbers_rounded,
          obscure: true,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(18)],
          textInputAction: TextInputAction.next,
        ),
        const FieldGap(),
        AppTextField(
          controller: _ifsc,
          label: 'IFSC code',
          hint: 'HDFC0001234',
          errorText: _errors['ifsc'],
          prefixIcon: Icons.account_balance_outlined,
          textCapitalization: TextCapitalization.characters,
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp('[A-Za-z0-9]')),
            LengthLimitingTextInputFormatter(11),
          ],
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => _save(),
        ),
        if (_formError != null) ...[
          const SizedBox(height: Space.l),
          Text(_formError!, style: AppType.bodySmall.copyWith(color: AppColors.danger)),
        ],
        const SizedBox(height: Space.xl),
        PrimaryButton(label: 'Save bank details', loading: _busy, onPressed: _save),
        if (b.saved) ...[
          const SizedBox(height: Space.m),
          SecondaryButton(label: 'Cancel', onPressed: () => setState(() => _editing = false)),
        ],
        const SizedBox(height: Space.l),
        const _PrivacyNote(),
      ],
    ),
  );
}

class _PrivacyNote extends StatelessWidget {
  const _PrivacyNote();

  @override
  Widget build(BuildContext context) => const GlassCard(
    padding: EdgeInsets.all(Space.l),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(Icons.lock_outline_rounded, color: AppColors.success),
        SizedBox(width: Space.m),
        Expanded(
          child: Text(
            'Your account number is stored encrypted and is only used to pay your rewards. '
            'We will never ask for your UPI PIN, card details, OTP or any payment from you.',
            style: AppType.bodySmall,
          ),
        ),
      ],
    ),
  );
}
