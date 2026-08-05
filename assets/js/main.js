/* =========================================================================
   PRO ITALIA Trattoria — сценарии сайта
   Без сторонних библиотек. Работает во всех современных браузерах.
   ========================================================================= */
(function () {
  'use strict';

  var $  = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ===================================================================
     НАСТРОЙКИ РЕСТОРАНА — правьте здесь
     =================================================================== */
  var CONFIG = {
    phone: '+7 (910) 600-22-21',
    phoneRaw: '+79106002221',
    address: 'г. Калуга, ул. Ленина, 86',
    /* Часы работы. 0 = воскресенье … 6 = суббота. Время в минутах от полуночи. */
    hours: {
      0: { open: 9 * 60, close: 23 * 60,      label: '9:00 — 23:00' },
      1: { open: 8 * 60, close: 23 * 60,      label: '8:00 — 23:00' },
      2: { open: 8 * 60, close: 23 * 60,      label: '8:00 — 23:00' },
      3: { open: 8 * 60, close: 23 * 60,      label: '8:00 — 23:00' },
      4: { open: 8 * 60, close: 23 * 60,      label: '8:00 — 23:00' },
      5: { open: 8 * 60, close: 24 * 60,      label: '8:00 — 00:00' },
      6: { open: 9 * 60, close: 24 * 60,      label: '9:00 — 00:00' }
    },
    dayNames: ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
  };

  /* ===================================================================
     Иконки (инлайн-SVG, чтобы не грузить лишние файлы)
     =================================================================== */
  var ICONS = {
    breakfast: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M17 8h1a4 4 0 1 1 0 8h-1"/><path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z"/><path d="M6 2v3M10 2v3M14 2v3"/></svg>',
    antipasti: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11h18"/><path d="M5 11a7 7 0 0 1 14 0"/><path d="M4 15h16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z"/><path d="M12 4v-.5"/></svg>',
    salad: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 21h10a5 5 0 0 0 5-5H2a5 5 0 0 0 5 5Z"/><path d="M12 11a4 4 0 0 0-4-4"/><path d="M12 11a4 4 0 0 1 4-4"/><path d="M12 11V3"/></svg>',
    soup: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10h16v2a8 8 0 0 1-16 0Z"/><path d="M2 21h20"/><path d="M8 6c0-1 1-1 1-2s-1-1-1-2M12 6c0-1 1-1 1-2s-1-1-1-2M16 6c0-1 1-1 1-2s-1-1-1-2"/></svg>',
    pasta: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 13h18a9 9 0 0 1-18 0Z"/><path d="M2 21h20"/><path d="M7 10c0-2 1-3 1-5M11 10c0-2 1-3 1-5M15 10c0-2 1-3 1-5"/></svg>',
    pizza: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2.5 20.5a1 1 0 0 0 1.3 1.35L12 18l8.2 3.85a1 1 0 0 0 1.3-1.35Z"/><circle cx="10" cy="11" r="1"/><circle cx="14.5" cy="13.5" r="1"/><circle cx="11" cy="16" r="1"/></svg>',
    risotto: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="14" rx="9" ry="6"/><path d="M8 12.5c1-1 2.5-1 3.5 0M13 15.5c1-1 2.5-1 3.5 0"/><path d="M12 8V5M9.5 5.5 12 3l2.5 2.5"/></svg>',
    main: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7a3 3 0 0 0 3 3 3 3 0 0 0 3-3V2"/><path d="M6 12v10"/><path d="M18 2c-2 0-3 3-3 6s1 4 3 4"/><path d="M18 2v20"/></svg>',
    dessert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 10h14l-2.2 10.3a2 2 0 0 1-2 1.7H9.2a2 2 0 0 1-2-1.7Z"/><path d="M5 10a7 7 0 0 1 14 0"/><path d="M12 3V1.5"/><circle cx="12" cy="3" r="1"/></svg>',
    drink: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16l-8 9Z"/><path d="M12 13v7"/><path d="M8 20h8"/></svg>',
    star: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="m12 2 2.9 6.26 6.85.72-5.1 4.6 1.44 6.72L12 16.9l-6.09 3.4 1.44-6.72-5.1-4.6 6.85-.72Z"/></svg>'
  };

  /* ===================================================================
     1. Шапка: фон при скролле + мобильное меню
     =================================================================== */
  function initHeader() {
    var header = $('.header');
    if (!header) return;

    var onScroll = function () {
      header.classList.toggle('is-stuck', window.scrollY > 24);
      var toTop = $('.to-top');
      if (toTop) toTop.classList.toggle('is-visible', window.scrollY > 700);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });

    var burger = $('.burger');
    var mobileNav = $('.mobile-nav');
    if (!burger || !mobileNav) return;

    var setOpen = function (open) {
      burger.setAttribute('aria-expanded', String(open));
      mobileNav.classList.toggle('is-open', open);
      document.body.classList.toggle('nav-open', open);
    };

    burger.addEventListener('click', function () {
      setOpen(burger.getAttribute('aria-expanded') !== 'true');
    });

    $$('.mobile-nav a').forEach(function (link) {
      link.addEventListener('click', function () { setOpen(false); });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setOpen(false);
    });
  }

  /* ===================================================================
     2. Живой статус «открыто / закрыто»
     =================================================================== */
  function pad(n) { return n < 10 ? '0' + n : String(n); }
  function fmt(mins) { return Math.floor(mins / 60) % 24 + ':' + pad(mins % 60); }

  function getStatus(now) {
    var day = now.getDay();
    var mins = now.getHours() * 60 + now.getMinutes();
    var today = CONFIG.hours[day];

    /* Заведение могло открыться вчера и работать после полуночи */
    var yesterday = CONFIG.hours[(day + 6) % 7];
    if (yesterday.close > 24 * 60 && mins < yesterday.close - 24 * 60) {
      return { open: true, text: 'Сейчас открыто · до ' + fmt(yesterday.close) };
    }

    if (mins >= today.open && mins < today.close) {
      return { open: true, text: 'Сейчас открыто · до ' + fmt(today.close) };
    }
    if (mins < today.open) {
      return { open: false, text: 'Закрыто · откроемся в ' + fmt(today.open) };
    }
    var tomorrow = CONFIG.hours[(day + 1) % 7];
    return { open: false, text: 'Закрыто · откроемся завтра в ' + fmt(tomorrow.open) };
  }

  function initStatus() {
    var nodes = $$('[data-status]');
    if (!nodes.length) return;

    var render = function () {
      var s = getStatus(new Date());
      nodes.forEach(function (node) {
        node.classList.toggle('is-open', s.open);
        node.classList.toggle('is-closed', !s.open);
        var label = $('.status__text', node);
        if (label) label.textContent = s.text;
      });
    };
    render();
    setInterval(render, 60000);

    /* Подсветка сегодняшнего дня в расписании */
    var todayIdx = new Date().getDay();
    $$('[data-day]').forEach(function (li) {
      if (Number(li.getAttribute('data-day')) === todayIdx) li.classList.add('is-today');
    });
  }

  /* ===================================================================
     3. Плавные якоря с учётом высоты шапки
     =================================================================== */
  function initAnchors() {
    $$('a[href^="#"]').forEach(function (link) {
      var id = link.getAttribute('href');
      if (!id || id === '#' || id.length < 2) return;

      link.addEventListener('click', function (e) {
        var target = document.getElementById(id.slice(1));
        if (!target) return;
        e.preventDefault();
        var offset = ($('.header') ? $('.header').offsetHeight : 0) + 12;
        var top = target.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top: top, behavior: 'smooth' });
        history.replaceState(null, '', id);
      });
    });
  }

  /* ===================================================================
     4. Подсветка активного пункта меню при скролле
     =================================================================== */
  function initScrollSpy() {
    var links = $$('.nav__link[href^="#"]');
    if (!links.length || !('IntersectionObserver' in window)) return;

    var sections = links
      .map(function (l) { return document.getElementById(l.getAttribute('href').slice(1)); })
      .filter(Boolean);

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        links.forEach(function (l) {
          l.classList.toggle('is-active', l.getAttribute('href') === '#' + entry.target.id);
        });
      });
    }, { rootMargin: '-45% 0px -50% 0px' });

    sections.forEach(function (s) { io.observe(s); });
  }

  /* ===================================================================
     5. Появление блоков при прокрутке
     =================================================================== */
  function initReveal() {
    var items = $$('[data-reveal]');
    if (!items.length) return;

    if (!('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('is-in'); });
      return;
    }

    var io = new IntersectionObserver(function (entries, obs) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        obs.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });

    items.forEach(function (el) { io.observe(el); });
  }

  /* ===================================================================
     6. Меню: отрисовка, вкладки, поиск
     =================================================================== */
  function money(value) {
    return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' ₽';
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function dishHtml(item) {
    var tags = (item.tags || []).map(function (t) {
      return '<span class="tag tag--' + t + '">' + escapeHtml(t) + '</span>';
    }).join('');
    if (item.veg) tags += '<span class="tag tag--veg" title="Вегетарианское">🌱 вег</span>';

    return '' +
      '<article class="dish">' +
        '<div class="dish__main">' +
          '<h4 class="dish__name">' + escapeHtml(item.name) + '</h4>' + tags +
          (item.desc ? '<p class="dish__desc">' + escapeHtml(item.desc) + '</p>' : '') +
          (item.weight ? '<div class="dish__meta"><span class="dish__weight">' + escapeHtml(item.weight) + '</span></div>' : '') +
        '</div>' +
        '<div class="dish__price">' + money(item.price) + '</div>' +
      '</article>';
  }

  function groupHtml(cat) {
    return '' +
      '<section class="menu-group" id="cat-' + cat.id + '" data-cat="' + cat.id + '" data-reveal>' +
        '<div class="menu-group__head">' +
          '<h3 class="menu-group__title">' + escapeHtml(cat.title) + '</h3>' +
          '<span class="menu-group__line"></span>' +
          '<span class="menu-group__count">' + cat.items.length + '</span>' +
        '</div>' +
        (cat.note ? '<p class="menu-group__note">' + escapeHtml(cat.note) + '</p>' : '') +
        '<div class="menu-list">' + cat.items.map(dishHtml).join('') + '</div>' +
      '</section>';
  }

  function initMenu() {
    var root = $('#menu-root');
    if (!root || !window.MENU_DATA) return;

    var data = window.MENU_DATA;
    var tabsBox = $('#menu-tabs');
    var search = $('#menu-search');
    var current = 'all';
    var query = '';

    /* --- вкладки категорий --- */
    if (tabsBox) {
      var tabsHtml = '<button class="menu-tab is-active" data-cat="all" type="button">Всё меню</button>';
      tabsHtml += data.categories.map(function (c) {
        return '<button class="menu-tab" data-cat="' + c.id + '" type="button">' +
               (ICONS[c.icon] || '') + escapeHtml(c.title) + '</button>';
      }).join('');
      tabsBox.innerHTML = tabsHtml;

      tabsBox.addEventListener('click', function (e) {
        var btn = e.target.closest('.menu-tab');
        if (!btn) return;
        current = btn.getAttribute('data-cat');
        $$('.menu-tab', tabsBox).forEach(function (b) { b.classList.toggle('is-active', b === btn); });
        render();
        /* прокручиваем список к началу, но не «прыгаем» вверх страницы */
        var top = root.getBoundingClientRect().top + window.scrollY - 200;
        if (window.scrollY > top) window.scrollTo({ top: top, behavior: 'smooth' });
      });
    }

    /* --- поиск --- */
    if (search) {
      var timer;
      search.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          query = search.value.trim().toLowerCase();
          render();
        }, 160);
      });
    }

    function render() {
      var cats = data.categories
        .filter(function (c) { return current === 'all' || c.id === current; })
        .map(function (c) {
          if (!query) return c;
          var items = c.items.filter(function (i) {
            return (i.name + ' ' + (i.desc || '')).toLowerCase().indexOf(query) !== -1;
          });
          return { id: c.id, title: c.title, icon: c.icon, note: c.note, items: items };
        })
        .filter(function (c) { return c.items.length > 0; });

      if (!cats.length) {
        root.innerHTML = '<div class="menu-empty"><strong>Ничего не нашлось</strong>' +
          '<p>Попробуйте другой запрос — или позвоните нам, подскажем: ' +
          '<a href="tel:' + CONFIG.phoneRaw + '">' + CONFIG.phone + '</a></p></div>';
        return;
      }

      root.innerHTML = cats.map(groupHtml).join('');
      initReveal();
    }

    render();
  }

  /* ===================================================================
     7. Блок «хиты» на главной
     =================================================================== */
  function initHighlights() {
    var box = $('#highlights');
    if (!box || !window.MENU_DATA) return;

    var data = window.MENU_DATA;
    var cards = (data.highlights || []).map(function (ref, idx) {
      var parts = ref.split('/');
      var cat = data.categories.filter(function (c) { return c.id === parts[0]; })[0];
      if (!cat) return '';
      var item = cat.items.filter(function (i) { return i.name === parts[1]; })[0];
      if (!item) return '';

      var badge = (item.tags && item.tags[0]) ? item.tags[0] : cat.title;

      return '' +
        '<article class="dish-card" data-reveal data-reveal-delay="' + (idx % 3 + 1) + '">' +
          '<div class="dish-card__media">' +
            '<img src="assets/img/dish-' + cat.id + '.svg" alt="' + escapeHtml(item.name) + '" loading="lazy" width="480" height="360">' +
            '<span class="dish-card__badge">' + escapeHtml(badge) + '</span>' +
          '</div>' +
          '<div class="dish-card__body">' +
            '<h3 class="dish-card__name">' + escapeHtml(item.name) + '</h3>' +
            '<p class="dish-card__desc">' + escapeHtml(item.desc || '') + '</p>' +
            '<div class="dish-card__foot">' +
              '<span class="dish-card__price">' + money(item.price) + '</span>' +
              '<span class="dish-card__weight">' + escapeHtml(item.weight || '') + '</span>' +
            '</div>' +
          '</div>' +
        '</article>';
    }).join('');

    box.innerHTML = cards;
    initReveal();
  }

  /* ===================================================================
     8. Форма бронирования
     =================================================================== */
  function initBooking() {
    var form = $('#booking-form');
    if (!form) return;

    /* минимальная дата — сегодня */
    var dateInput = $('#b-date', form);
    if (dateInput) {
      var now = new Date();
      var iso = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
      dateInput.min = iso;
      if (!dateInput.value) dateInput.value = iso;
    }

    /* маска телефона */
    var phoneInput = $('#b-phone', form);
    if (phoneInput) {
      phoneInput.addEventListener('input', function () {
        var digits = phoneInput.value.replace(/\D/g, '').replace(/^8/, '7').replace(/^([^7])/, '7$1');
        var d = digits.slice(0, 11);
        var out = '+7';
        if (d.length > 1) out += ' (' + d.slice(1, 4);
        if (d.length >= 5) out += ') ' + d.slice(4, 7);
        if (d.length >= 8) out += '-' + d.slice(7, 9);
        if (d.length >= 10) out += '-' + d.slice(9, 11);
        phoneInput.value = out;
      });
    }

    function setError(field, message) {
      var wrap = field.closest('.field');
      if (!wrap) return;
      wrap.classList.toggle('has-error', Boolean(message));
      field.setAttribute('aria-invalid', message ? 'true' : 'false');
      var err = $('.field__error', wrap);
      if (err && message) err.textContent = message;
    }

    /* Ошибка исчезает, как только гость начал исправлять поле */
    $$('input, select, textarea', form).forEach(function (field) {
      var clear = function () {
        var wrap = field.closest('.field');
        if (wrap && wrap.classList.contains('has-error')) setError(field, '');
      };
      field.addEventListener('input', clear);
      field.addEventListener('change', clear);
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var ok = true;

      var name = $('#b-name', form);
      var phone = $('#b-phone', form);
      var guests = $('#b-guests', form);
      var date = $('#b-date', form);
      var time = $('#b-time', form);
      var comment = $('#b-comment', form);

      if (!name.value.trim() || name.value.trim().length < 2) {
        setError(name, 'Пожалуйста, укажите имя'); ok = false;
      } else setError(name, '');

      if (phone.value.replace(/\D/g, '').length < 11) {
        setError(phone, 'Введите номер полностью'); ok = false;
      } else setError(phone, '');

      if (!date.value) { setError(date, 'Выберите дату'); ok = false; } else setError(date, '');
      if (!time.value) { setError(time, 'Выберите время'); ok = false; } else setError(time, '');

      if (!ok) {
        var firstError = $('.field.has-error input, .field.has-error select', form);
        if (firstError) firstError.focus();
        return;
      }

      /* Заявка собирается в текст и уходит в WhatsApp администратору.
         Как подключить обычную отправку на почту — смотрите README.md */
      var text =
        'Бронь столика — PRO ITALIA' +
        '\nИмя: ' + name.value.trim() +
        '\nТелефон: ' + phone.value.trim() +
        '\nГостей: ' + guests.value +
        '\nДата: ' + date.value +
        '\nВремя: ' + time.value +
        (comment.value.trim() ? '\nПожелания: ' + comment.value.trim() : '');

      window.open('https://wa.me/' + CONFIG.phoneRaw.replace('+', '') + '?text=' + encodeURIComponent(text), '_blank', 'noopener');

      $('.form__fields', form).style.display = 'none';
      var success = $('.form__success', form);
      if (success) {
        success.classList.add('is-visible');
        success.setAttribute('tabindex', '-1');
        success.focus();
      }
    });
  }

  /* ===================================================================
     9. Галерея-лайтбокс
     =================================================================== */
  function initLightbox() {
    var items = $$('.gallery__item');
    if (!items.length) return;

    var box = document.createElement('div');
    box.className = 'lightbox';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-label', 'Просмотр фотографии');
    box.innerHTML = '<button class="lightbox__close" type="button" aria-label="Закрыть">✕</button><img alt="">';
    document.body.appendChild(box);

    var img = $('img', box);
    var lastFocused = null;

    var close = function () {
      box.classList.remove('is-open');
      document.body.classList.remove('nav-open');
      if (lastFocused) lastFocused.focus();
    };

    items.forEach(function (item) {
      item.addEventListener('click', function () {
        var source = $('img', item);
        if (!source) return;
        lastFocused = item;
        img.src = source.currentSrc || source.src;
        img.alt = source.alt || '';
        box.classList.add('is-open');
        document.body.classList.add('nav-open');
        $('.lightbox__close', box).focus();
      });
    });

    box.addEventListener('click', function (e) {
      if (e.target === box || e.target.closest('.lightbox__close')) close();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && box.classList.contains('is-open')) close();
    });
  }

  /* ===================================================================
     10. Мелочи
     =================================================================== */
  function initMisc() {
    var year = $('#year');
    if (year) year.textContent = new Date().getFullYear();

    var toTop = $('.to-top');
    if (toTop) {
      toTop.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }

    /* Ленивая подгрузка тяжёлых iframe (карта, отзывы) — быстрее первая отрисовка */
    var frames = $$('iframe[data-src]');
    var load = function (frame) {
      frame.addEventListener('load', function () { frame.classList.add('is-loaded'); });
      frame.src = frame.getAttribute('data-src');
    };

    if (frames.length && 'IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (entries, obs) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          load(entry.target);
          obs.unobserve(entry.target);
        });
      }, { rootMargin: '300px' });
      frames.forEach(function (f) { io.observe(f); });
    } else {
      frames.forEach(load);
    }
  }

  /* ===================================================================
     Запуск
     =================================================================== */
  function init() {
    initHeader();
    initStatus();
    initAnchors();
    initScrollSpy();
    initMenu();
    initHighlights();
    initBooking();
    initLightbox();
    initMisc();
    initReveal();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
