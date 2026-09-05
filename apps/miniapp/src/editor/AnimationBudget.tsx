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
        {Array.from({ length: ANIMATION_BUDGET }, (_, index) => (
          <i key={index} className={index < used ? 'is-on' : undefined} />
        ))}
      </span>
      <span className="budget__text">
        {/* «6 из 5» — арифметическая бессмыслица, за бюджетом счёт идёт иначе. */}
        {over
          ? `Анимация ${used}, бюджет ${ANIMATION_BUDGET}`
          : `Анимация ${used} из ${ANIMATION_BUDGET}`}
      </span>
    </span>
  );
}
