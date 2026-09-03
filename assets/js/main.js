/* Кутуза — логика сайта: контакты, меню, навигация, анимации появления. */
(function () {
  'use strict';

  /**
   * Контакты заведения.
   * ВАЖНО: на карточке Яндекс.Карт номер показан частично — «+7 (926) 988-…».
   * Подставьте полный номер здесь, и он обновится во всех ссылках сразу
   * (шапка, блок контактов, кнопка звонка, WhatsApp, Telegram).
   */
  var CONTACT = {
    phone: '+7 (926) 988-00-00',   // TODO: полный номер
    phoneRaw: '79269880000',       // TODO: тот же номер, только цифры
    telegram: 'https://t.me/'      // TODO: ссылка на канал/аккаунт в Telegram
  };

  /* ── Контакты в разметке ─────────────────────────────────────────── */
  function applyContacts() {
    document.querySelectorAll('[data-phone-link]').forEach(function (el) {
      el.href = 'tel:+' + CONTACT.phoneRaw;
      if (el.dataset.phoneLink === 'text' || /^\+?[\d\s()\-–]+$/.test(el.textContent.trim())) {
        el.textContent = CONTACT.phone;
      }
    });
    document.querySelectorAll('[data-wa-link]').forEach(function (el) {
      el.href = 'https://wa.me/' + CONTACT.phoneRaw;
    });
    document.querySelectorAll('[data-tg-link]').forEach(function (el) {
      el.href = CONTACT.telegram;
    });
  }

  /* ── Меню ────────────────────────────────────────────────────────── */
  var TAG_LABELS = {
    'халяль': 'Халяль',
    'острое': 'Остро',
    'новинка': 'Новинка',
    'хит': 'Хит'
  };

  function priceText(price) {
    if (price === null || price === undefined) return 'уточняйте';
    return price.toLocaleString('ru-RU') + ' ₽';
  }

  function buildCard(item) {
    var card = document.createElement('article');
    card.className = 'dish reveal';

    var head = document.createElement('div');
    head.className = 'dish-head';

    var name = document.createElement('h3');
    name.textContent = item.name;
    head.appendChild(name);

    var price = document.createElement('p');
    price.className = 'dish-price' + (item.price == null ? ' dish-price-soft' : '');
    price.textContent = priceText(item.price);
    head.appendChild(price);

    card.appendChild(head);

    if (item.desc) {
      var desc = document.createElement('p');
      desc.className = 'dish-desc';
      desc.textContent = item.desc;
      card.appendChild(desc);
    }

    var meta = document.createElement('div');
    meta.className = 'dish-meta';

    if (item.weight) {
      var weight = document.createElement('span');
      weight.className = 'dish-weight';
      weight.textContent = item.weight;
      meta.appendChild(weight);
    }

    (item.tags || []).forEach(function (tag) {
      var chip = document.createElement('span');
      chip.className = 'tag tag-' + tag;
      chip.textContent = TAG_LABELS[tag] || tag;
      meta.appendChild(chip);
    });

    if (meta.childNodes.length) card.appendChild(meta);
    return card;
  }

  function renderCategory(category, grid) {
    grid.textContent = '';

    if (category.lead) {
      var lead = document.createElement('p');
      lead.className = 'menu-lead';
      lead.textContent = category.lead;
      grid.appendChild(lead);
    }

    var list = document.createElement('div');
    list.className = 'dish-list';
    category.items.forEach(function (item) {
      list.appendChild(buildCard(item));
    });
    grid.appendChild(list);

    observeReveals(grid);
  }

  function initMenu() {
    var tabsEl = document.getElementById('menu-tabs');
    var grid = document.getElementById('menu-grid');
    var data = window.KUTUZA_MENU;
    if (!tabsEl || !grid || !data || !data.length) return;

    var buttons = data.map(function (category, index) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'menu-tab';
      btn.textContent = category.title;
      btn.setAttribute('role', 'tab');
      btn.id = 'tab-' + category.id;
      btn.setAttribute('aria-controls', 'menu-grid');
      btn.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
      btn.tabIndex = index === 0 ? 0 : -1;
      tabsEl.appendChild(btn);
      return btn;
    });

    function select(index) {
      buttons.forEach(function (btn, i) {
        var active = i === index;
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
        btn.tabIndex = active ? 0 : -1;
      });
      grid.setAttribute('aria-labelledby', buttons[index].id);
      renderCategory(data[index], grid);
    }

    buttons.forEach(function (btn, index) {
      btn.addEventListener('click', function () {
        select(index);
      });
      btn.addEventListener('keydown', function (event) {
        var next = null;
        if (event.key === 'ArrowRight') next = (index + 1) % buttons.length;
        if (event.key === 'ArrowLeft') next = (index - 1 + buttons.length) % buttons.length;
        if (next === null) return;
        event.preventDefault();
        select(next);
        buttons[next].focus();
      });
    });

    grid.setAttribute('role', 'tabpanel');
    select(0);
  }

  /* ── Мобильная навигация ─────────────────────────────────────────── */
  function initNav() {
    var burger = document.getElementById('burger');
    var nav = document.getElementById('nav');
    if (!burger || !nav) return;

    function close() {
      document.body.classList.remove('nav-open');
      burger.setAttribute('aria-expanded', 'false');
    }

    burger.addEventListener('click', function () {
      var open = document.body.classList.toggle('nav-open');
      burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    nav.addEventListener('click', function (event) {
      if (event.target.tagName === 'A') close();
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') close();
    });
  }

  /* ── Шапка: тень при прокрутке ───────────────────────────────────── */
  function initHeaderState() {
    var header = document.querySelector('.site-header');
    if (!header) return;
    var ticking = false;

    function update() {
      header.classList.toggle('is-scrolled', window.scrollY > 12);
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    }, { passive: true });
    update();
  }

  /* ── Появление блоков при прокрутке ──────────────────────────────── */
  var revealObserver = null;

  function observeReveals(root) {
    var targets = (root || document).querySelectorAll('.reveal:not(.is-visible)');
    if (!revealObserver) {
      targets.forEach(function (el) { el.classList.add('is-visible'); });
      return;
    }
    targets.forEach(function (el) { revealObserver.observe(el); });
  }

  function initReveals() {
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!reduced && 'IntersectionObserver' in window) {
      revealObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          revealObserver.unobserve(entry.target);
        });
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0 });
    }
    observeReveals(document);
  }

  /* ── Подсветка активного пункта меню ─────────────────────────────── */
  function initScrollSpy() {
    var links = Array.prototype.slice.call(document.querySelectorAll('.nav a[href^="#"]'));
    var sections = links
      .map(function (link) { return document.querySelector(link.getAttribute('href')); })
      .filter(Boolean);
    if (!sections.length || !('IntersectionObserver' in window)) return;

    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        links.forEach(function (link) {
          link.classList.toggle('is-active', link.getAttribute('href') === '#' + entry.target.id);
        });
      });
    }, { rootMargin: '-45% 0px -50% 0px' });

    sections.forEach(function (section) { spy.observe(section); });
  }

  function initYear() {
    var year = document.getElementById('year');
    if (year) year.textContent = new Date().getFullYear();
  }

  document.addEventListener('DOMContentLoaded', function () {
    applyContacts();
    initMenu();
    initNav();
    initHeaderState();
    initReveals();
    initScrollSpy();
    initYear();
  });
})();
