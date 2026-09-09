import { Body, Controller, Get, Param, Post, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { CsrfGuard } from '../common/guards/csrf.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { KycTrainingService } from './kyc-training.service';
import { SubmitChallengeDto } from './dto/submit-challenge.dto';
import { User } from '@prisma/client';

@Controller('kyc-training')
@UseGuards(JwtAuthGuard, CsrfGuard)
export class KycTrainingController {
  constructor(private readonly kycTrainingService: KycTrainingService) {}

  @Get('next-challenge')
  async next(@CurrentUser() user: User) {
    return this.kycTrainingService.issueNextChallenge(user.id);
  }

  @Post('attempts/:attemptId/submit')
  async submit(
    @CurrentUser() user: User,
    @Param('attemptId') attemptId: string,
    @Body() dto: SubmitChallengeDto,
  ) {
    return this.kycTrainingService.submitChallenge(user.id, attemptId, dto);
  }
}
