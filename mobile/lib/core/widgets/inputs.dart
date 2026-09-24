import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';

class AppTextField extends StatelessWidget {
  const AppTextField({
    super.key,
    required this.controller,
    required this.label,
    this.hint,
    this.errorText,
    this.keyboardType,
    this.obscure = false,
    this.prefixText,
    this.prefixIcon,
    this.suffix,
    this.inputFormatters,
    this.textCapitalization = TextCapitalization.none,
    this.autofillHints,
    this.textInputAction,
    this.onSubmitted,
    this.onChanged,
    this.maxLength,
    this.enabled = true,
    this.helper,
  });

  final TextEditingController controller;
  final String label;
  final String? hint;
  final String? errorText;
  final TextInputType? keyboardType;
  final bool obscure;
  final String? prefixText;
  final IconData? prefixIcon;
  final Widget? suffix;
  final List<TextInputFormatter>? inputFormatters;
  final TextCapitalization textCapitalization;
  final Iterable<String>? autofillHints;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onSubmitted;
  final ValueChanged<String>? onChanged;
  final int? maxLength;
  final bool enabled;
  final String? helper;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      enabled: enabled,
      keyboardType: keyboardType,
      obscureText: obscure,
      enableSuggestions: !obscure,
      autocorrect: false,
      inputFormatters: inputFormatters,
      textCapitalization: textCapitalization,
      autofillHints: autofillHints,
      textInputAction: textInputAction,
      onSubmitted: onSubmitted,
      onChanged: onChanged,
      maxLength: maxLength,
      style: AppType.body.copyWith(color: AppColors.textPrimary),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        errorText: errorText,
        helperText: helper,
        helperStyle: AppType.caption,
        helperMaxLines: 3,
        errorMaxLines: 3,
        counterText: '',
        prefixText: prefixText,
        prefixStyle: AppType.body.copyWith(color: AppColors.textSecondary),
        prefixIcon: prefixIcon == null ? null : Icon(prefixIcon, color: AppColors.textMuted),
        suffixIcon: suffix,
      ),
    );
  }
}

/// A password field with a show/hide toggle.
class PasswordField extends StatefulWidget {
  const PasswordField({
    super.key,
    required this.controller,
    this.label = 'Password',
    this.errorText,
    this.helper,
    this.newPassword = false,
    this.onSubmitted,
  });

  final TextEditingController controller;
  final String label;
  final String? errorText;
  final String? helper;
  final bool newPassword;
  final ValueChanged<String>? onSubmitted;

  @override
  State<PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<PasswordField> {
  bool _hidden = true;

  @override
  Widget build(BuildContext context) => AppTextField(
    controller: widget.controller,
    label: widget.label,
    errorText: widget.errorText,
    helper: widget.helper,
    obscure: _hidden,
    prefixIcon: Icons.lock_outline_rounded,
    autofillHints: [widget.newPassword ? AutofillHints.newPassword : AutofillHints.password],
    textInputAction: TextInputAction.done,
    onSubmitted: widget.onSubmitted,
    maxLength: 128,
    suffix: IconButton(
      tooltip: _hidden ? 'Show password' : 'Hide password',
      icon: Icon(_hidden ? Icons.visibility_outlined : Icons.visibility_off_outlined, color: AppColors.textMuted),
      onPressed: () => setState(() => _hidden = !_hidden),
    ),
  );
}

/// Indian mobile number: fixed +91 prefix, 10 digits.
class PhoneField extends StatelessWidget {
  const PhoneField({super.key, required this.controller, this.errorText, this.textInputAction});

  final TextEditingController controller;
  final String? errorText;
  final TextInputAction? textInputAction;

  @override
  Widget build(BuildContext context) => AppTextField(
    controller: controller,
    label: 'Mobile number',
    hint: '98765 43210',
    prefixText: '+91  ',
    prefixIcon: Icons.phone_iphone_rounded,
    errorText: errorText,
    keyboardType: TextInputType.phone,
    autofillHints: const [AutofillHints.telephoneNumberNational],
    textInputAction: textInputAction ?? TextInputAction.next,
    inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(10)],
  );
}

/// Client-side checks only shape the input; the server validates again.
abstract final class Validators {
  static String? indianMobile(String value) {
    if (!RegExp(r'^[6-9]\d{9}$').hasMatch(value.trim())) return 'Enter your 10-digit mobile number.';
    return null;
  }

  static String? newPassword(String value) {
    if (value.length < 8) return 'Use at least 8 characters.';
    if (value.length > 128) return 'Use at most 128 characters.';
    return null;
  }
}

class FieldGap extends StatelessWidget {
  const FieldGap({super.key});

  @override
  Widget build(BuildContext context) => const SizedBox(height: Space.l);
}
