import { Controller, Get, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { User } from '@prisma/client';

@Controller('users')
@UseGuards(JwtAuthGuard)
export class UsersController {
  @Get('me')
  me(@CurrentUser() user: User) {
    // Deliberately narrow — never return passwordHash or internal-only fields.
    return {
      id: user.id,
      mobile: user.mobileE164,
      status: user.status,
      role: user.role,
      referralCode: user.referralCode,
      createdAt: user.createdAt,
    };
  }
}
