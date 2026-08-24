/* ═══════════════════════════════════════════════════════════════════════════
   Банкетный зал «Кондырев» — скрипты сайта
   ───────────────────────────────────────────────────────────────────────────
   Ванильный JS, без библиотек. Всё оформлено небольшими независимыми
   модулями: если что-то одно убрать, остальное продолжит работать.

   Содержание:
     0. Настройки (CONFIG) — телефон, e-mail для заявок
     1. Шапка: тень при скролле
     2. Мобильное меню
     3. Подсветка активного пункта меню (scroll-spy)
     4. Появление блоков при скролле
     5. Параллакс в hero
     6. Кнопка «Наверх»
     7. Лайтбокс галереи
     8. Форма заявки: маска телефона, валидация, отправка
     9. Мелочи: год в подвале, предвыбор типа мероприятия
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ═══ 0. НАСТРОЙКИ ═══════════════════════════════════════════════════════
     ┌───────────────────────────────────────────────────────────────────────┐
     │ TODO: укажите почту, на которую хотите получать заявки.               │
     │ Пока стоит заглушка — заявки открываются в почтовой программе гостя.  │
     └───────────────────────────────────────────────────────────────────────┘ */
  var CONFIG = {
    email: 'zakaz@example.com',        // TODO: заменить на реальный e-mail
    phone: '+7 (920) 876-02-22',
    phoneHref: 'tel:+79208760222',
    thanksPage: 'thanks.html'
  };

  var $  = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };

  // Системная настройка «уменьшить движение» — отключаем параллакс и анимации
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;


  /* ═══ 1. ШАПКА: тень появляется, когда страница прокручена ════════════════ */
  (function stickyHeader() {
    var header = $('#header');
    if (!header) return;

    var update = function () {
      header.classList.toggle('is-stuck', window.scrollY > 8);
    };
    update();
    window.addEventListener('scroll', update, { passive: true });
  })();


  /* ═══ 2. МОБИЛЬНОЕ МЕНЮ ══════════════════════════════════════════════════ */
  (function mobileNav() {
    var burger  = $('#burger');
    var nav     = $('#nav');
    var overlay = $('#navOverlay');
    if (!burger || !nav || !overlay) return;

    var open = function () {
      nav.classList.add('is-open');
      document.getElementById('header').classList.add('is-nav-open');
      burger.setAttribute('aria-expanded', 'true');
      burger.setAttribute('aria-label', 'Закрыть меню');
      overlay.hidden = false;
      // requestAnimationFrame нужен, чтобы сработал transition после снятия hidden
      requestAnimationFrame(function () { overlay.classList.add('is-visible'); });
      document.body.classList.add('is-locked');
    };

    var close = function () {
      nav.classList.remove('is-open');
      document.getElementById('header').classList.remove('is-nav-open');
      burger.setAttribute('aria-expanded', 'false');
      burger.setAttribute('aria-label', 'Открыть меню');
      overlay.classList.remove('is-visible');
      document.body.classList.remove('is-locked');
      setTimeout(function () {
        if (!nav.classList.contains('is-open')) overlay.hidden = true;
      }, 320);
    };

    var isOpen = function () { return nav.classList.contains('is-open'); };

    burger.addEventListener('click', function () { isOpen() ? close() : open(); });
    overlay.addEventListener('click', close);

    // Клик по пункту меню — переходим к секции и закрываем панель
    $$('a', nav).forEach(function (link) {
      link.addEventListener('click', function () { if (isOpen()) close(); });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) { close(); burger.focus(); }
    });

    // Если экран стал широким, панель больше не нужна — снимаем блокировку
    window.matchMedia('(min-width: 900px)').addEventListener('change', function (e) {
      if (e.matches && isOpen()) close();
    });
  })();


  /* ═══ 3. SCROLL-SPY: подсветка активного пункта меню ══════════════════════ */
  (function scrollSpy() {
    var links = $$('.nav__link');
    if (!links.length || !('IntersectionObserver' in window)) return;

    // Собираем пары «секция → ссылка» по href="#id"
    var map = {};
    var sections = [];
    links.forEach(function (link) {
      var id = link.getAttribute('href');
      if (!id || id.charAt(0) !== '#') return;
      var section = document.querySelector(id);
      if (!section) return;
      map[section.id] = link;
      sections.push(section);
    });

    var visible = {};
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        visible[entry.target.id] = entry.isIntersecting;
      });
      // Активной считаем самую верхнюю из видимых секций
      var activeId = null;
      for (var i = 0; i < sections.length; i++) {
        if (visible[sections[i].id]) { activeId = sections[i].id; break; }
      }
      links.forEach(function (link) {
        link.classList.toggle('is-active', activeId !== null && map[activeId] === link);
      });
    }, {
      // Окно наблюдения: полоса чуть ниже шапки — так активная секция
      // переключается ровно тогда, когда её видно в основном поле зрения
      rootMargin: '-45% 0px -50% 0px',
      threshold: 0
    });

    sections.forEach(function (s) { observer.observe(s); });
  })();


  /* ═══ 4. ПОЯВЛЕНИЕ БЛОКОВ ПРИ СКРОЛЛЕ ════════════════════════════════════ */
  (function revealOnScroll() {
    var items = $$('.reveal');
    if (!items.length) return;

    // Нет поддержки наблюдателя или выключены анимации — просто показываем всё
    if (!('IntersectionObserver' in window) || reduceMotion) {
      items.forEach(function (el) { el.classList.add('is-visible'); });
      return;
    }

    var observer = new IntersectionObserver(function (entries, obs) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        obs.unobserve(entry.target);   // анимируем один раз
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });

    items.forEach(function (el) { observer.observe(el); });
  })();


  /* ═══ 5. ПАРАЛЛАКС В HERO ════════════════════════════════════════════════
     Фон сдвигается медленнее страницы. Считаем в requestAnimationFrame,
     чтобы не тормозить скролл. На мобильных отключаем — там это лишняя
     нагрузка и заметные подёргивания. */
  (function heroParallax() {
    var layer = $('[data-parallax]');
    if (!layer || reduceMotion) return;
    if (!window.matchMedia('(min-width: 900px) and (pointer: fine)').matches) return;

    var ticking = false;

    var render = function () {
      var offset = Math.min(window.scrollY, window.innerHeight) * 0.28;
      layer.style.transform = 'translate3d(0,' + offset.toFixed(1) + 'px,0)';
      ticking = false;
    };

    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(render);
    }, { passive: true });

    render();
  })();


  /* ═══ 6. КНОПКА «НАВЕРХ» ═════════════════════════════════════════════════ */
  (function toTop() {
    var btn = $('#toTop');
    if (!btn) return;

    var update = function () {
      var show = window.scrollY > window.innerHeight * 0.8;
      if (show) {
        btn.hidden = false;
        requestAnimationFrame(function () { btn.classList.add('is-visible'); });
      } else {
        btn.classList.remove('is-visible');
        setTimeout(function () {
          if (!btn.classList.contains('is-visible')) btn.hidden = true;
        }, 320);
      }
    };

    btn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
    });

    update();
    window.addEventListener('scroll', update, { passive: true });
  })();


  /* ═══ 7. ЛАЙТБОКС ГАЛЕРЕИ ════════════════════════════════════════════════
     Открывается по клику на фото, листается стрелками, свайпом и клавишами.
     Без JS ссылки просто открывают файл изображения — галерея не ломается. */
  (function lightbox() {
    var box = $('#lightbox');
    var links = $$('.gallery__link');
    if (!box || !links.length) return;

    var img       = $('#lightboxImg');
    var caption   = $('#lightboxCaption');
    var counter   = $('#lightboxCounter');
    var btnClose  = $('.lightbox__close', box);
    var btnPrev   = $('.lightbox__prev', box);
    var btnNext   = $('.lightbox__next', box);
    var index     = 0;
    var lastFocus = null;

    var show = function (i) {
      index = (i + links.length) % links.length;      // зацикливаем перелистывание
      var link = links[index];
      var thumb = link.querySelector('img');
      img.src = link.getAttribute('href');
      img.alt = thumb ? thumb.alt : '';
      caption.textContent = link.dataset.caption || (thumb ? thumb.alt : '');
      counter.textContent = (index + 1) + ' / ' + links.length;
    };

    var open = function (i) {
      lastFocus = document.activeElement;
      show(i);
      box.hidden = false;
      document.body.classList.add('is-locked');
      btnClose.focus();
    };

    var close = function () {
      box.hidden = true;
      document.body.classList.remove('is-locked');
      img.src = '';
      if (lastFocus) lastFocus.focus();
    };

    links.forEach(function (link, i) {
      link.addEventListener('click', function (e) {
        e.preventDefault();
        open(i);
      });
    });

    btnClose.addEventListener('click', close);
    btnPrev.addEventListener('click', function () { show(index - 1); });
    btnNext.addEventListener('click', function () { show(index + 1); });

    // Клик по тёмному фону (не по фото и не по кнопке) — закрыть
    box.addEventListener('click', function (e) {
      if (e.target === box || e.target.classList.contains('lightbox__figure')) close();
    });

    document.addEventListener('keydown', function (e) {
      if (box.hidden) return;
      if (e.key === 'Escape')     { close(); }
      if (e.key === 'ArrowLeft')  { show(index - 1); }
      if (e.key === 'ArrowRight') { show(index + 1); }
      // Удерживаем фокус внутри диалога, пока он открыт
      if (e.key === 'Tab') {
        var focusable = [btnClose, btnPrev, btnNext];
        var pos = focusable.indexOf(document.activeElement);
        e.preventDefault();
        var next = e.shiftKey ? pos - 1 : pos + 1;
        focusable[(next + focusable.length) % focusable.length].focus();
      }
    });

    // Свайп пальцем по фотографии
    var startX = 0;
    box.addEventListener('touchstart', function (e) {
      startX = e.changedTouches[0].clientX;
    }, { passive: true });
    box.addEventListener('touchend', function (e) {
      var delta = e.changedTouches[0].clientX - startX;
      if (Math.abs(delta) > 45) show(delta < 0 ? index + 1 : index - 1);
    }, { passive: true });
  })();


  /* ═══ 8. ФОРМА ЗАЯВКИ ════════════════════════════════════════════════════ */
  (function bookingForm() {
    var form = $('#bookingForm');
    if (!form) return;

    var status  = $('#formStatus');
    var fName   = $('#f-name');
    var fPhone  = $('#f-phone');
    var fDate   = $('#f-date');
    var fEvent  = $('#f-event');
    var fText   = $('#f-comment');
    var fAgree  = $('#f-agree');

    /* — Дата: запрещаем выбирать прошедший день — */
    if (fDate) {
      var today = new Date();
      var pad = function (n) { return String(n).padStart(2, '0'); };
      fDate.min = today.getFullYear() + '-' + pad(today.getMonth() + 1) + '-' + pad(today.getDate());
    }

    /* — Маска телефона: приводим ввод к виду +7 (920) 876-02-22 —
       Важно: сначала снимаем наш собственный префикс «+7», иначе его семёрка
       на следующем шаге снова попадёт в разбор и сдвинет весь номер. */
    var formatPhone = function (value) {
      var rest = String(value).replace(/^\s*\+?7/, '');
      var digits = rest.replace(/\D/g, '');

      // Код страны, введённый вручную или вставленный из буфера.
      // Российские коды городов и операторов не начинаются с 8 или 0,
      // поэтому ведущую восьмёрку убираем всегда.
      if (digits.charAt(0) === '8' || digits.charAt(0) === '0') digits = digits.slice(1);
      digits = digits.slice(0, 10);
      if (!digits) return '';

      // Разделители добавляем только перед непустой группой — иначе номер
      // нельзя стереть: маска дорисовывала бы скобку обратно на каждый Backspace.
      var out = '+7 (' + digits.slice(0, 3);
      if (digits.length > 3) out += ') ' + digits.slice(3, 6);
      if (digits.length > 6) out += '-' + digits.slice(6, 8);
      if (digits.length > 8) out += '-' + digits.slice(8, 10);
      return out;
    };

    if (fPhone) {
      fPhone.addEventListener('input', function () {
        var caretAtEnd = fPhone.selectionStart === fPhone.value.length;
        fPhone.value = formatPhone(fPhone.value);
        if (caretAtEnd) fPhone.setSelectionRange(fPhone.value.length, fPhone.value.length);
      });
    }

    /* — Показ и снятие ошибки у конкретного поля — */
    var setError = function (field, message) {
      var box = document.querySelector('[data-error-for="' + field.id + '"]');
      if (box) box.textContent = message || '';
      field.classList.toggle('is-invalid', Boolean(message));
      if (message) field.setAttribute('aria-invalid', 'true');
      else field.removeAttribute('aria-invalid');
    };

    /* — Правила проверки одного поля — */
    var validateField = function (field) {
      if (!field) return true;
      var value = (field.value || '').trim();

      if (field === fName) {
        if (!value)            return setError(field, 'Пожалуйста, представьтесь'), false;
        if (value.length < 2)  return setError(field, 'Слишком короткое имя'), false;
      }

      if (field === fPhone) {
        var digits = value.replace(/\D/g, '');
        if (!value)              return setError(field, 'Без телефона мы не сможем перезвонить'), false;
        if (digits.length !== 11) return setError(field, 'Введите номер полностью: +7 (___) ___-__-__'), false;
      }

      if (field === fDate && value) {
        // Сравниваем календарные дни, поэтому обнуляем время у «сегодня»
        var chosen = new Date(value + 'T00:00:00');
        var now = new Date(); now.setHours(0, 0, 0, 0);
        if (isNaN(chosen.getTime())) return setError(field, 'Проверьте дату'), false;
        if (chosen < now)            return setError(field, 'Эта дата уже прошла'), false;
      }

      if (field === fAgree && !field.checked) {
        return setError(field, 'Нужно согласие на обработку данных'), false;
      }

      setError(field, '');
      return true;
    };

    // Проверяем поле при уходе с него и снимаем ошибку, как только её исправили
    [fName, fPhone, fDate, fAgree].forEach(function (field) {
      if (!field) return;
      var event = field.type === 'checkbox' ? 'change' : 'blur';
      field.addEventListener(event, function () { validateField(field); });
      field.addEventListener('input', function () {
        if (field.classList.contains('is-invalid')) validateField(field);
      });
    });

    /* — Сборка письма из полей формы — */
    var buildMail = function () {
      var lines = [
        'Заявка с сайта банкетного зала «Кондырев»',
        '',
        'Имя: ' + fName.value.trim(),
        'Телефон: ' + fPhone.value.trim(),
        'Дата мероприятия: ' + (fDate && fDate.value ? fDate.value : 'не указана'),
        'Тип мероприятия: ' + (fEvent && fEvent.value ? fEvent.value : 'не указан'),
        '',
        'Комментарий:',
        (fText && fText.value.trim()) || '—',
        '',
        'Отправлено со страницы: ' + window.location.href
      ];
      var subject = 'Заявка с сайта' + (fEvent && fEvent.value ? ' — ' + fEvent.value : '');
      return 'mailto:' + CONFIG.email +
             '?subject=' + encodeURIComponent(subject) +
             '&body='    + encodeURIComponent(lines.join('\n'));
    };

    form.addEventListener('submit', function (e) {
      e.preventDefault();

      // Проверяем все поля и переводим фокус на первое проблемное
      var fields = [fName, fPhone, fDate, fAgree];
      var firstInvalid = null;
      fields.forEach(function (field) {
        if (!validateField(field) && !firstInvalid) firstInvalid = field;
      });

      if (firstInvalid) {
        status.className = 'form__status form__status--error';
        status.textContent = 'Проверьте, пожалуйста, отмеченные поля.';
        firstInvalid.focus();
        return;
      }

      /* ┌─ ПОДКЛЮЧЕНИЕ БЭКЕНДА ─────────────────────────────────────────────┐
         │ Сейчас работает mailto-фоллбэк: письмо открывается в почтовой     │
         │ программе гостя, и он нажимает «Отправить». Это работает без      │
         │ сервера, но часть заявок теряется. Как только появится приём      │
         │ заявок — замените блок ниже на один из вариантов:                 │
         │                                                                   │
         │ 1) Telegram-бот (заявка приходит в чат за минуту на настройку):   │
         │    var TOKEN = '...', CHAT_ID = '...';                            │
         │    fetch('https://api.telegram.org/bot' + TOKEN + '/sendMessage', │
         │      { method: 'POST',                                            │
         │        headers: { 'Content-Type': 'application/json' },           │
         │        body: JSON.stringify({ chat_id: CHAT_ID, text: text }) })  │
         │      .then(onSuccess).catch(onError);                             │
         │    ВНИМАНИЕ: токен бота в коде страницы виден всем. Для боевого   │
         │    использования проксируйте запрос через свой скрипт на сервере. │
         │                                                                   │
         │ 2) Formspree / Getform (готовый приём форм на почту, без кода):   │
         │    fetch('https://formspree.io/f/ВАШ_ID',                         │
         │      { method: 'POST', body: new FormData(form),                  │
         │        headers: { Accept: 'application/json' } })                 │
         │      .then(onSuccess).catch(onError);                             │
         │                                                                   │
         │ 3) Своя CRM или PHP-обработчик на хостинге:                       │
         │    fetch('/send.php', { method: 'POST', body: new FormData(form) })│
         │                                                                   │
         │ В любом варианте оставьте переход на thanks.html — это удобная    │
         │ цель для Яндекс.Метрики и Google Analytics.                       │
         └───────────────────────────────────────────────────────────────────┘ */

      status.className = 'form__status';
      status.textContent = 'Открываем почтовую программу… Если письмо не создалось, позвоните нам: ' + CONFIG.phone;

      window.location.href = buildMail();

      // Небольшая пауза, чтобы браузер успел передать ссылку почтовому клиенту
      setTimeout(function () { window.location.href = CONFIG.thanksPage; }, 1400);
    });
  })();


  /* ═══ 9. МЕЛОЧИ ══════════════════════════════════════════════════════════ */

  // Год в копирайте — чтобы подвал не устаревал
  (function currentYear() {
    var el = $('#year');
    if (el) el.textContent = new Date().getFullYear();
  })();

  // Ссылки «Обсудить свадьбу», «Обсудить юбилей» и т.п. заранее выбирают
  // нужный пункт в списке типов мероприятия — гостю меньше кликов
  (function preselectEvent() {
    var select = $('#f-event');
    if (!select) return;

    $$('[data-event]').forEach(function (link) {
      link.addEventListener('click', function () {
        var wanted = link.dataset.event;
        $$('option', select).forEach(function (option) {
          if (option.value === wanted || option.textContent === wanted) select.value = option.value || option.textContent;
        });
      });
    });
  })();

})();
