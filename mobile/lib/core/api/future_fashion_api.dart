import 'api_client.dart';
import 'models.dart';

/// The app's view of the server (docs/API.md). Screens depend on this
/// interface; tests supply fakes, and nothing ships a mock as real data.
abstract interface class FutureFashionApi {
  Stream<void> get sessionEnded;

  Future<PublicConfig> config();
  Future<Captcha> captcha();
  Future<bool> referralCodeValid(String code);

  Future<AuthResult> signup({
    required String phone,
    required String password,
    required String? referralCode,
    required String captchaId,
    required String captchaAnswer,
    required String idempotencyKey,
  });
  Future<AuthResult> login({required String phone, required String password, String? captchaId, String? captchaAnswer});
  Future<void> logout();
  Future<Me> me();

  Future<VerificationSession> openVerification();
  Future<VerificationSession> verificationStatus();

  Future<Dashboard> dashboard();
  Future<ReferralSummary> referralSummary();
  Future<Paged<DirectReferral>> directReferrals({String? cursor, int limit = 20});
  Future<ShareInfo> shareInfo();

  Future<Wallet> wallet();
  Future<BankDetails> bankDetails();
  Future<BankDetails> saveBankDetails({
    required String accountHolderName,
    required String accountNumber,
    required String ifsc,
    required String idempotencyKey,
  });
  Future<Paged<Withdrawal>> withdrawals({String? cursor, int limit = 20});
  Future<Withdrawal> requestWithdrawal({required int amountPaise, required String idempotencyKey});
}

class HttpFutureFashionApi implements FutureFashionApi {
  HttpFutureFashionApi(this._client);

  final ApiClient _client;

  @override
  Stream<void> get sessionEnded => _client.sessionEnded;

  @override
  Future<PublicConfig> config() async => PublicConfig.fromJson(await _client.get('/v1/config', auth: false));

  @override
  Future<Captcha> captcha() async => Captcha.fromJson(await _client.get('/v1/captcha', auth: false));

  @override
  Future<bool> referralCodeValid(String code) async {
    final body = await _client.get('/v1/referral-codes/${Uri.encodeComponent(code)}', auth: false);
    return body['valid'] == true;
  }

  @override
  Future<AuthResult> signup({
    required String phone,
    required String password,
    required String? referralCode,
    required String captchaId,
    required String captchaAnswer,
    required String idempotencyKey,
  }) async => AuthResult.fromJson(
    await _client.post(
      '/v1/auth/signup',
      auth: false,
      idempotencyKey: idempotencyKey,
      body: {
        'phone': phone,
        'password': password,
        'referral_code': referralCode,
        'captcha_id': captchaId,
        'captcha_answer': captchaAnswer,
      },
    ),
  );

  @override
  Future<AuthResult> login({
    required String phone,
    required String password,
    String? captchaId,
    String? captchaAnswer,
  }) async => AuthResult.fromJson(
    await _client.post(
      '/v1/auth/login',
      auth: false,
      body: {'phone': phone, 'password': password, 'captcha_id': captchaId, 'captcha_answer': captchaAnswer},
    ),
  );

  @override
  Future<void> logout() => _client.postNoContent('/v1/auth/logout');

  @override
  Future<Me> me() async => Me.fromJson(await _client.get('/v1/me'));

  @override
  Future<VerificationSession> openVerification() async =>
      VerificationSession.fromJson(await _client.post('/v1/telegram/verification-session'));

  @override
  Future<VerificationSession> verificationStatus() async =>
      VerificationSession.fromJson(await _client.get('/v1/telegram/verification-session'));

  @override
  Future<Dashboard> dashboard() async => Dashboard.fromJson(await _client.get('/v1/dashboard'));

  @override
  Future<ReferralSummary> referralSummary() async =>
      ReferralSummary.fromJson(await _client.get('/v1/referrals/summary'));

  @override
  Future<Paged<DirectReferral>> directReferrals({String? cursor, int limit = 20}) async => Paged.fromJson(
    await _client.get('/v1/referrals/direct', query: {'limit': limit, 'cursor': ?cursor}),
    DirectReferral.fromJson,
  );

  @override
  Future<ShareInfo> shareInfo() async => ShareInfo.fromJson(await _client.get('/v1/referral/share'));

  @override
  Future<Wallet> wallet() async => Wallet.fromJson(await _client.get('/v1/wallet'));

  @override
  Future<BankDetails> bankDetails() async => BankDetails.fromJson(await _client.get('/v1/bank-details'));

  @override
  Future<BankDetails> saveBankDetails({
    required String accountHolderName,
    required String accountNumber,
    required String ifsc,
    required String idempotencyKey,
  }) async => BankDetails.fromJson(
    await _client.post(
      '/v1/bank-details',
      idempotencyKey: idempotencyKey,
      body: {'account_holder_name': accountHolderName, 'account_number': accountNumber, 'ifsc': ifsc},
    ),
  );

  @override
  Future<Paged<Withdrawal>> withdrawals({String? cursor, int limit = 20}) async => Paged.fromJson(
    await _client.get('/v1/withdrawals', query: {'limit': limit, 'cursor': ?cursor}),
    Withdrawal.fromJson,
  );

  @override
  Future<Withdrawal> requestWithdrawal({required int amountPaise, required String idempotencyKey}) async =>
      Withdrawal.fromJson(
        await _client.post('/v1/withdrawals', idempotencyKey: idempotencyKey, body: {'amount_paise': amountPaise}),
      );
}
