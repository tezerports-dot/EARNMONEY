import { Controller, Get, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { ReferralsService } from './referrals.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { User } from '@prisma/client';

@Controller('referrals')
@UseGuards(JwtAuthGuard)
export class ReferralsController {
  constructor(
    private readonly referralsService: ReferralsService,
    private readonly eligibility: EligibilityService,
  ) {}

  /** Everything the referral screen renders, in one round trip. */
  @Get('me')
  async myReferrals(@CurrentUser() user: User) {
    const [referrals, progress, stats] = await Promise.all([
      this.referralsService.listMyReferrals(user.id),
      this.eligibility.getProgress(user.id),
      this.referralsService.getReferralStats(user.id),
    ]);
    return { referralCode: user.referralCode, referrals, progress, stats };
  }
}
