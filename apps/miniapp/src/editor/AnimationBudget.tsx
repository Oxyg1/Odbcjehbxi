import { ANIMATION_BUDGET } from '@plsdonate/shared';

interface AnimationBudgetProps {
  used: number;
}

/**
 * Бюджет анимации на виду постоянно: пользователь должен понимать цену
 * следующего анимированного слоя до того, как стенд начнёт лагать у зрителей.
 */
export function AnimationBudget({ used }: AnimationBudgetProps) {
  const over = used > ANIMATION_BUDGET;
  return (
    <span className={over ? 'budget budget--over' : 'budget'}>
      <span className="budget__dots" aria-hidden>
        {Array.from({ length: Math.max(ANIMATION_BUDGET, used) }, (_, index) => (
          <i key={index} className={index < used ? 'is-on' : undefined} />
        ))}
      </span>
      <span className="budget__text">
        Анимация {used} из {ANIMATION_BUDGET}
      </span>
    </span>
  );
}
