import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/models.dart';
import '../../core/config/config_controller.dart';
import '../../core/config/support_contact.dart';
import '../../core/formatters/dates.dart';
import '../../core/formatters/inr.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';

/// Fills the bundled legal text with the server's current values.
String fillLegal(String text, PublicConfig cfg) {
  final support = cfg.supportEmail ?? cfg.supportUrl ?? 'the Support page in the app';
  return text
      .replaceAll('{{company}}', cfg.companyName)
      .replaceAll('{{legal_name}}', cfg.companyLegalName ?? cfg.companyName)
      .replaceAll('{{support}}', support)
      .replaceAll('{{reward}}', formatPaise(cfg.level1RewardPaise))
      .replaceAll('{{payout_date}}', formatIstDate(cfg.campaign.payoutOpensAt))
      .replaceAll('{{min_withdrawal}}', formatPaise(cfg.minWithdrawalPaise));
}

/// Renders the small Markdown subset used by the bundled texts.
List<Widget> renderSimpleMarkdown(String text) {
  final widgets = <Widget>[];
  for (final block in text.split(RegExp(r'\n\s*\n'))) {
    final lines = block.trim().split('\n');
    if (lines.first.startsWith('# ')) {
      widgets.add(Semantics(header: true, child: Text(lines.first.substring(2), style: AppType.headline)));
      widgets.add(const SizedBox(height: Space.l));
      continue;
    }
    if (lines.first.startsWith('## ')) {
      widgets.add(const SizedBox(height: Space.m));
      widgets.add(Semantics(header: true, child: Text(lines.first.substring(3), style: AppType.title)));
      widgets.add(const SizedBox(height: Space.s));
      continue;
    }
    for (final line in lines) {
      final bullet = line.startsWith('- ');
      final content = bullet ? line.substring(2) : line;
      final spans = <TextSpan>[];
      final parts = content.split('**');
      for (var i = 0; i < parts.length; i++) {
        spans.add(TextSpan(text: parts[i], style: i.isOdd ? AppType.label : null));
      }
      final paragraph = Text.rich(TextSpan(style: AppType.body, children: spans));
      widgets.add(
        Padding(
          padding: const EdgeInsets.only(bottom: Space.s),
          child: bullet
              ? Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Padding(
                      padding: EdgeInsets.only(top: 9, right: Space.m),
                      child: Icon(Icons.circle, size: 6, color: AppColors.gold),
                    ),
                    Expanded(child: paragraph),
                  ],
                )
              : paragraph,
        ),
      );
    }
    widgets.add(const SizedBox(height: Space.s));
  }
  return widgets;
}

final _legalText = FutureProvider.family<String, String>((ref, name) => rootBundle.loadString('assets/legal/$name.md'));

class LegalScreen extends ConsumerWidget {
  const LegalScreen({super.key, required this.document, required this.title});

  /// "terms" or "privacy".
  final String document;
  final String title;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cfg = ref.watch(configProvider).requireValue.config;
    final text = ref.watch(_legalText(document));
    final onlineUrl = document == 'terms' ? cfg.termsUrl : cfg.privacyUrl;
    return AppScreen(
      title: title,
      children: [
        if (onlineUrl != null) ...[
          SecondaryButton(
            label: 'Read the latest version online',
            icon: Icons.open_in_new_rounded,
            onPressed: () => launchUrl(Uri.parse(onlineUrl), mode: LaunchMode.externalApplication),
          ),
          const SizedBox(height: Space.xl),
        ],
        AsyncBody<String>(
          value: text,
          onRetry: () => ref.invalidate(_legalText(document)),
          data: (raw) =>
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: renderSimpleMarkdown(fillLegal(raw, cfg))),
        ),
      ],
    );
  }
}

/// The reward rules, built from live configuration (CLAUDE.md §33).
class RulesScreen extends ConsumerWidget {
  const RulesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cfg = ref.watch(configProvider).requireValue.config;
    final c = cfg.campaign;
    final reward = formatPaise(cfg.level1RewardPaise);
    Widget rule(IconData icon, String title, String body) => Padding(
      padding: const EdgeInsets.only(bottom: Space.m),
      child: GlassCard(
        padding: const EdgeInsets.all(Space.l),
        child: MergeSemantics(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: AppColors.gold),
              const SizedBox(width: Space.m),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: AppType.label),
                    const SizedBox(height: Space.xs),
                    Text(body, style: AppType.bodySmall),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
    return AppScreen(
      title: 'Reward rules',
      children: [
        Text(
          'Run by ${cfg.companyName}. These figures come from our server and are always current.',
          style: AppType.body,
        ),
        const SizedBox(height: Space.xl),
        rule(Icons.money_off_rounded, 'Free to join', 'You never pay anything to join, earn or withdraw.'),
        rule(
          Icons.card_giftcard_rounded,
          '$reward per direct referral',
          'You earn $reward for each person who signs up with your code and completes Telegram verification '
              'while the campaign is running.',
        ),
        rule(
          Icons.account_tree_rounded,
          'Levels 2–4 pay ₹0',
          'Your referral table also counts the people your friends invited (levels 2 to 4). '
              'Those levels don’t earn rewards.',
        ),
        rule(
          Icons.event_rounded,
          'Payout date',
          'Rewards stay pending until ${formatIstDate(c.payoutOpensAt)}. From then you can withdraw to your bank '
              'account. Minimum withdrawal: ${formatPaise(cfg.minWithdrawalPaise)}.',
        ),
        rule(
          Icons.savings_rounded,
          'A limited budget',
          'Rewards come from a promotional budget. When it runs out, or the campaign is paused or ends '
              '(${formatIstDate(c.endsAt)}), new rewards stop. The app tells you when that happens.',
        ),
        rule(
          Icons.gavel_rounded,
          'Fair play',
          'One account per person. Fake accounts and other dishonest referrals can lead to suspension.',
        ),
        rule(Icons.receipt_long_rounded, 'Taxes', 'Rewards may count as income for you under Indian tax rules.'),
      ],
    );
  }
}

class SupportScreen extends ConsumerWidget {
  const SupportScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cfg = ref.watch(configProvider).requireValue.config;
    final contact = supportContact(cfg);
    Widget faq(String q, String a) => Padding(
      padding: const EdgeInsets.only(bottom: Space.m),
      child: GlassCard(
        padding: const EdgeInsets.all(Space.l),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(q, style: AppType.label),
            const SizedBox(height: Space.xs),
            Text(a, style: AppType.bodySmall),
          ],
        ),
      ),
    );
    return AppScreen(
      title: 'Support',
      children: [
        if (contact != null) ...[
          PrimaryButton(
            label: 'Contact support',
            icon: Icons.support_agent_rounded,
            onPressed: () => launchUrl(contact, mode: LaunchMode.externalApplication),
          ),
          if (cfg.supportEmail case final email?) ...[
            const SizedBox(height: Space.s),
            SelectableText(email, style: AppType.bodySmall, textAlign: TextAlign.center),
          ],
          const SizedBox(height: Space.xl),
        ],
        faq(
          'My friend signed up but I see no reward',
          'Rewards are added when your friend completes Telegram verification. Until then they show as “Verifying”.',
        ),
        faq(
          'Telegram says my number doesn’t match',
          'Use the Telegram account registered to the same number you signed up with. You can get a new link in the app.',
        ),
        faq(
          'When can I withdraw?',
          'From ${formatIstDate(cfg.campaign.payoutOpensAt)}, to a bank account in your name.',
        ),
        faq(
          'Will anyone ask me to pay to receive my rewards?',
          'No. ${cfg.companyName} never asks for fees, UPI PINs or OTPs. If someone does, it’s a scam: don’t pay.',
        ),
        faq(
          'I forgot my password',
          contact == null
              ? 'Support contact details will appear here soon. Your account and rewards stay safe meanwhile.'
              : 'Contact support above to reset it.',
        ),
      ],
    );
  }
}
