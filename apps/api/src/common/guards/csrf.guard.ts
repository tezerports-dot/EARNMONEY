import { CanActivate, ExecutionContext, ForbiddenException, Injectable } from '@nestjs/common';

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

/**
 * Double-submit cookie CSRF protection: the frontend reads the non-httpOnly
 * `csrf_token` cookie (set at login, see AuthController) and echoes it back
 * in the `x-csrf-token` header on every state-changing request. Since a
 * cross-site page cannot read another origin's cookies, it cannot forge this
 * header, even though the browser auto-attaches the auth cookie.
 */
@Injectable()
export class CsrfGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest();

    if (SAFE_METHODS.has(request.method)) {
      return true;
    }

    const cookieToken = request.cookies?.['csrf_token'];
    const headerToken = request.headers['x-csrf-token'];

    if (!cookieToken || !headerToken || cookieToken !== headerToken) {
      throw new ForbiddenException('CSRF validation failed.');
    }

    return true;
  }
}
