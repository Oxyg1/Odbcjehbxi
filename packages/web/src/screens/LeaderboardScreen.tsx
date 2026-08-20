import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { formatCompact, type Leaderboard, type LeaderboardScope } from '@tgdonate/shared';
import { api } from '../lib/api.js';
import { cn } from '../lib/cn.js';
import { haptics } from '../lib/telegram.js';
import { Avatar, Card, Skeleton } from '../components/ui/primitives.js';

const SCOPES: Array<{ id: LeaderboardScope; label: string }> = [
  { id: 'DAILY', label: 'Today' },
  { id: 'WEEKLY', label: 'Week' },
  { id: 'ALL_TIME', label: 'All time' },
];

/** Whale ranks. The status ladder the whole donation loop feeds. */
export function LeaderboardScreen() {
  const [scope, setScope] = useState<LeaderboardScope>('DAILY');
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    void (async () => {
      try {
        const response = await api.leaderboard(scope, 50);
        if (!cancelled) setBoard(response.leaderboard);
      } catch {
        if (!cancelled) setBoard(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [scope]);

  return (
    <div className="safe-top safe-bottom flex flex-col gap-3 px-4">
      <header>
        <h1 className="text-[24px] leading-[28px] font-black tracking-[-0.6px]">Whale Ranks</h1>
        <p className="text-[13px] text-alpha-2">Top donors. Updated as the Stars land.</p>
      </header>

      <div className="glass-shadow flex gap-1 rounded-full bg-surface-2 p-1">
        {SCOPES.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => {
              haptics.select();
              setScope(option.id);
            }}
            className={cn(
              'flex-1 rounded-full py-2 text-[13px] font-bold transition-colors',
              scope === option.id ? 'bg-accent text-[#0b0b0b]' : 'text-alpha-2',
            )}
          >
            {option.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 8 }, (_, index) => (
            <Skeleton key={index} className="h-[56px] w-full squircle-lg" />
          ))}
        </div>
      ) : !board || board.rows.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-6 text-center">
          <span className="text-[28px]">🐋</span>
          <p className="text-[15px] font-bold">Nobody has donated yet</p>
          <p className="text-[13px] text-alpha-2">First one on the board takes the crown.</p>
        </Card>
      ) : (
        <div className="flex flex-col gap-1.5">
          {board.rows.map((row, index) => (
            <motion.div
              key={row.user.id}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(index * 0.025, 0.4) }}
            >
              <Card
                className={cn(
                  'flex items-center gap-3 p-2.5',
                  row.rank <= 3 && 'ring-1',
                )}
                style={
                  row.rank <= 3
                    ? { boxShadow: `var(--glass-shadow), 0 0 0 1px ${rankColor(row.rank)}44` }
                    : undefined
                }
              >
                <span
                  className="w-7 shrink-0 text-center text-[15px] font-black"
                  style={{ color: rankColor(row.rank) }}
                >
                  {row.rank <= 3 ? ['🥇', '🥈', '🥉'][row.rank - 1] : row.rank}
                </span>
                <Avatar
                  src={row.user.photoUrl}
                  name={row.user.displayName}
                  size={36}
                  ring={row.rank <= 3 ? rankColor(row.rank) : null}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-bold">{row.user.displayName}</p>
                  {row.user.username ? (
                    <p className="truncate text-[12px] text-alpha-2">@{row.user.username}</p>
                  ) : null}
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-[15px] font-black text-accent">
                    {formatCompact(row.starsDonated)} ⭐
                  </p>
                  {row.giftsDonated > 0 ? (
                    <p className="text-[11px] text-alpha-2">🎁 {row.giftsDonated}</p>
                  ) : null}
                </div>
              </Card>
            </motion.div>
          ))}

          {/* The viewer's own row, pinned when they are outside the top N. */}
          {board.viewer && !board.rows.some((row) => row.user.id === board.viewer?.user.id) ? (
            <Card className="mt-2 flex items-center gap-3 border border-accent/30 p-2.5">
              <span className="w-7 shrink-0 text-center text-[14px] font-black text-accent">
                {board.viewer.rank}
              </span>
              <Avatar src={board.viewer.user.photoUrl} name={board.viewer.user.displayName} size={36} />
              <p className="min-w-0 flex-1 truncate text-[14px] font-bold">You</p>
              <p className="shrink-0 text-[15px] font-black text-accent">
                {formatCompact(board.viewer.starsDonated)} ⭐
              </p>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  );
}

function rankColor(rank: number): string {
  if (rank === 1) return '#f1aa05';
  if (rank === 2) return '#c5c5b9';
  if (rank === 3) return '#d88b6b';
  return '#6d6d71';
}
