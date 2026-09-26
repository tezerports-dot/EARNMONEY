import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../providers.dart';

/// Public configuration plus the difference between the phone's clock and
/// the server's. Countdowns and "is it payout day yet" use server time,
/// never the phone's clock alone (CLAUDE.md §34).
class ConfigState {
  const ConfigState(this.config, this.clockOffset);

  final PublicConfig config;
  final Duration clockOffset;

  DateTime serverNow() => DateTime.now().toUtc().add(clockOffset);
}

class ConfigController extends AsyncNotifier<ConfigState> {
  @override
  Future<ConfigState> build() async {
    final sentAt = DateTime.now().toUtc();
    final config = await ref.watch(apiProvider).config();
    final receivedAt = DateTime.now().toUtc();
    // Assume the server read its clock halfway through the round trip.
    final midpoint = sentAt.add(receivedAt.difference(sentAt) ~/ 2);
    return ConfigState(config, config.serverNow.difference(midpoint));
  }

  Future<void> reload() async {
    ref.invalidateSelf();
    await future;
  }
}

final configProvider = AsyncNotifierProvider<ConfigController, ConfigState>(ConfigController.new);
