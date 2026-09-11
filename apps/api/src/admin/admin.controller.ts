import { Body, Controller, Get, Param, Patch, Post, UseGuards } from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { IsBoolean } from 'class-validator';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { CsrfGuard } from '../common/guards/csrf.guard';
import { RolesGuard } from '../common/guards/roles.guard';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AdminConfigService } from './admin-config.service';
import { AdminScenariosService } from './admin-scenarios.service';
import { UpdateConfigDto } from './dto/update-config.dto';
import { CreateScenarioDto } from './dto/create-scenario.dto';
import { User } from '@prisma/client';

class SetActiveDto {
  @IsBoolean()
  isActive: boolean;
}

/**
 * Admin surface. This is the first place `@Roles()` is actually applied —
 * RolesGuard and the decorator existed but were never used, so until now every
 * endpoint was either public or "any logged-in user".
 *
 * Guard order matters: JwtAuthGuard must run first to populate `request.user`,
 * or RolesGuard has nothing to check.
 */
@Controller('admin')
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('ADMIN_SUPERADMIN')
export class AdminController {
  constructor(
    private readonly config: AdminConfigService,
    private readonly scenarios: AdminScenariosService,
  ) {}

  /** Current thresholds, with the ceilings that constrain them. */
  @Get('config')
  async listConfig() {
    return this.config.listSettings();
  }

  /**
   * Change one threshold. Rejected if the value would make the target
   * unreachable — see AdminConfigService.
   */
  @Patch('config/:key')
  @UseGuards(CsrfGuard)
  @Throttle({ default: { limit: 30, ttl: 60_000 } })
  async updateConfig(
    @Param('key') key: string,
    @Body() dto: UpdateConfigDto,
    @CurrentUser() user: User,
  ) {
    return this.config.update(key, dto.value, user.id);
  }

  /** The practice-document bank, plus whether the current target is reachable. */
  @Get('scenarios')
  async listScenarios() {
    return this.scenarios.list();
  }

  @Post('scenarios')
  @UseGuards(CsrfGuard)
  @Throttle({ default: { limit: 60, ttl: 60_000 } })
  async createScenario(@Body() dto: CreateScenarioDto, @CurrentUser() user: User) {
    return this.scenarios.create(dto, user.id);
  }

  @Patch('scenarios/:id/active')
  @UseGuards(CsrfGuard)
  async setScenarioActive(
    @Param('id') id: string,
    @Body() dto: SetActiveDto,
    @CurrentUser() user: User,
  ) {
    return this.scenarios.setActive(id, dto.isActive, user.id);
  }
}
