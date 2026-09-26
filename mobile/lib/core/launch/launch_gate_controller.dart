import 'package:flutter_riverpod/flutter_riverpod.dart';

/// True only after the server clears the gate for the current foreground session.
final gatePassedProvider = StateProvider<bool>((ref) => false);
