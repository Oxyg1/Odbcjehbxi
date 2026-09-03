import { useCallback, useMemo, useState } from "react";
import Smoke from "./components/Smoke";
import Header from "./components/Header";
import Hero from "./components/Hero";
import MenuSection from "./components/MenuSection";
import Craft from "./components/Craft";
import Gallery from "./components/Gallery";
import Reviews from "./components/Reviews";
import OrderForm, { type CartLine } from "./components/OrderForm";
import Contact from "./components/Contact";
import Footer from "./components/Footer";
import { MENU, type Dish } from "./data";
import { useAnchorOffset } from "./hooks";

const ALL_DISHES = MENU.flatMap((c) => c.dishes);

export default function App() {
  const [cart, setCart] = useState<Record<string, number>>({});
  const onNav = useAnchorOffset();

  const addDish = useCallback((dish: Dish) => {
    setCart((c) => ({ ...c, [dish.id]: (c[dish.id] ?? 0) + 1 }));
  }, []);

  const inc = useCallback((id: string) => {
    setCart((c) => ({ ...c, [id]: (c[id] ?? 0) + 1 }));
  }, []);

  const dec = useCallback((id: string) => {
    setCart((c) => {
      const next = { ...c };
      const qty = (next[id] ?? 0) - 1;
      if (qty <= 0) delete next[id];
      else next[id] = qty;
      return next;
    });
  }, []);

  const clear = useCallback(() => setCart({}), []);

  const lines = useMemo<CartLine[]>(
    () =>
      ALL_DISHES.filter((d) => (cart[d.id] ?? 0) > 0).map((d) => ({
        dish: d,
        qty: cart[d.id],
      })),
    [cart],
  );

  const count = useMemo(() => lines.reduce((s, l) => s + l.qty, 0), [lines]);

  return (
    <div className="relative min-h-screen font-body antialiased">
      {/* Первая цель Tab: увести клавиатуру мимо шапки к содержимому */}
      <a href="#menu" className="skip-link">
        К меню и заказу
      </a>
      <Smoke />
      <Header cartCount={count} onNav={onNav} />
      <main id="main" className="relative z-10">
        <Hero onNav={onNav} />
        <MenuSection onAdd={addDish} />
        <Craft />
        <Gallery />
        <Reviews />
        <OrderForm lines={lines} onInc={inc} onDec={dec} onClear={clear} onNav={onNav} />
        <Contact />
      </main>
      <div className="relative z-10">
        <Footer onNav={onNav} />
      </div>
    </div>
  );
}
