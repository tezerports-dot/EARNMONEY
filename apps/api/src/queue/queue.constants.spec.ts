import { deliverUpdateJobId } from './queue.constants';

describe('deliverUpdateJobId', () => {
  it('is deterministic, so replaying a slot re-enqueues nothing', () => {
    expect(deliverUpdateJobId('abc', 3)).toBe(deliverUpdateJobId('abc', 3));
  });

  it('distinguishes users and versions', () => {
    expect(deliverUpdateJobId('a', 1)).not.toBe(deliverUpdateJobId('b', 1));
    expect(deliverUpdateJobId('a', 1)).not.toBe(deliverUpdateJobId('a', 2));
  });

  it('contains no colon — BullMQ rejects custom ids containing one', () => {
    // Found the hard way: a ':' separator makes addBulk throw at runtime while
    // every unit test that mocks the queue still passes.
    expect(deliverUpdateJobId('550e8400-e29b-41d4-a716-446655440000', 7)).not.toContain(':');
  });
});
