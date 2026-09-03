/** Фоновая среда сайта: тёплый дым, угольное свечение и зерно плёнки */
export default function Smoke() {
  return (
    <>
      <div className="fixed inset-0 z-0 pointer-events-none" aria-hidden="true">
        {/* база */}
        <div className="absolute inset-0 bg-coal" />
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(120% 90% at 50% 0%, rgba(58,47,31,0.5) 0%, rgba(20,16,11,0) 55%)",
          }}
        />
        {/* дымовые массы */}
        <div
          className="smoke-a absolute -top-[18%] -left-[12%] w-[58vw] h-[58vw] rounded-full blur-[130px]"
          style={{ background: "rgba(96,80,56,0.22)" }}
        />
        <div
          className="smoke-b absolute top-[24%] -right-[16%] w-[52vw] h-[52vw] rounded-full blur-[140px]"
          style={{ background: "rgba(70,56,38,0.24)" }}
        />
        <div
          className="smoke-c absolute -bottom-[22%] left-[16%] w-[46vw] h-[46vw] rounded-full blur-[150px]"
          style={{ background: "rgba(255,92,38,0.09)" }}
        />
        <div
          className="smoke-b absolute top-[58%] left-[38%] w-[34vw] h-[34vw] rounded-full blur-[120px]"
          style={{ background: "rgba(255,176,46,0.06)" }}
        />
        {/* виньетка */}
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(140% 100% at 50% 45%, rgba(20,16,11,0) 55%, rgba(12,9,6,0.75) 100%)",
          }}
        />
      </div>
      {/* зерно */}
      <div
        className="noise fixed inset-0 z-[70] pointer-events-none opacity-[0.07] mix-blend-overlay"
        aria-hidden="true"
      />
    </>
  );
}
