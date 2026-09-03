/* Кутуза — прогрессивное улучшение.
   Страница полностью работает без этого файла: меню, контакты и все разделы
   отдаются в разметке. Скрипт добавляет вкладки меню, мобильную навигацию,
   подсветку текущего раздела и подставляет телефон, когда он заполнен. */
(function () {
  'use strict';

  /**
   * Контакты заведения.
   *
   * На карточке Яндекс.Карт номер показан частично («+7 (926) 988-…»),
   * поэтому здесь ПУСТО: выдуманных цифр на сайте быть не должно.
   * Впишите настоящий номер — и он появится в блоке контактов и в нижней
   * кнопке звонка на мобильных. Пока поле пустое, кнопка честно ведёт
   * на карточку Яндекса, где номер есть.
   *
   *   phone    — как показывать: '+7 (926) 988-12-34'
   *   phoneRaw — только цифры для tel: и WhatsApp: '79269881234'
   *   whatsapp — true, если по этому номеру отвечают в WhatsApp
   */
  var CONTACT = {
    phone: '',
    phoneRaw: '',
    whatsapp: false,
    yandex: 'https://yandex.ru/maps/org/kutuza/1084941511/'
  };

  var hasPhone = /^\d{10,15}$/.test(CONTACT.phoneRaw) && CONTACT.phone.length > 0;

  /* ── Телефон и нижняя полоса звонка ──────────────────────────────── */
  function initContacts() {
    if (hasPhone) {
      var cell = document.querySelector('[data-contact-phone]');
      if (cell) {
        cell.textContent = '';
        var link = document.createElement('a');
        link.href = 'tel:+' + CONTACT.phoneRaw;
        link.className = 'phone-partial';
        link.textContent = CONTACT.phone;
        cell.appendChild(link);

        if (CONTACT.whatsapp) {
          var wa = document.createElement('a');
          wa.href = 'https://wa.me/' + CONTACT.phoneRaw;
          wa.target = '_blank';
          wa.rel = 'noopener';
          wa.textContent = 'Написать в WhatsApp';
          cell.appendChild(document.createElement('br'));
          cell.appendChild(wa);
        }
      }
    }

    var bar = document.createElement('a');
    bar.className = 'call-bar';
    if (hasPhone) {
      bar.href = 'tel:+' + CONTACT.phoneRaw;
      bar.textContent = 'Позвонить ' + CONTACT.phone;
    } else {
      bar.href = CONTACT.yandex;
      bar.target = '_blank';
      bar.rel = 'noopener';
      bar.textContent = 'Позвонить';
      var note = document.createElement('small');
      note.textContent = 'номер — в карточке на Яндекс.Картах';
      bar.appendChild(note);
    }
    document.body.appendChild(bar);
  }

  /* ── Меню: секции разметки становятся вкладками ──────────────────── */
  function initMenuTabs() {
    var tabsEl = document.getElementById('menu-tabs');
    var grid = document.getElementById('menu-grid');
    if (!tabsEl || !grid) return;

    var panels = Array.prototype.slice.call(grid.querySelectorAll('.menu-cat'));
    if (panels.length < 2) return;

    var buttons = panels.map(function (panel, index) {
      var heading = panel.querySelector('h3');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'menu-tab';
      btn.id = 'tab-' + panel.id;
      btn.textContent = heading ? heading.textContent : 'Раздел ' + (index + 1);
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-controls', panel.id);
      tabsEl.appendChild(btn);

      // Заголовок раздела дублирует надпись на вкладке, поэтому visually-hidden,
      // а не hidden: иначе он выпадает из структуры заголовков и следующий
      // h4 повисает под h2.
      if (heading) heading.classList.add('visually-hidden');
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', btn.id);
      panel.tabIndex = 0;
      return btn;
    });

    tabsEl.setAttribute('role', 'tablist');
    tabsEl.setAttribute('aria-label', 'Разделы меню');
    tabsEl.hidden = false;

    function select(index, moveFocus) {
      buttons.forEach(function (btn, i) {
        var active = i === index;
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
        btn.tabIndex = active ? 0 : -1;
        panels[i].hidden = !active;
      });
      if (moveFocus) buttons[index].focus();
    }

    buttons.forEach(function (btn, index) {
      btn.addEventListener('click', function () { select(index); });
      btn.addEventListener('keydown', function (event) {
        var next = null;
        if (event.key === 'ArrowRight') next = (index + 1) % buttons.length;
        else if (event.key === 'ArrowLeft') next = (index - 1 + buttons.length) % buttons.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = buttons.length - 1;
        if (next === null) return;
        event.preventDefault();
        select(next, true);
      });
    });

    select(0);
  }

  /* ── Мобильная навигация ─────────────────────────────────────────── */
  function initNav() {
    var burger = document.getElementById('burger');
    var nav = document.getElementById('nav');
    if (!burger || !nav) return;

    var links = Array.prototype.slice.call(nav.querySelectorAll('a'));

    // Панель скрыта трансформацией, поэтому её ссылки нужно убрать
    // из порядка табуляции, иначе фокус уходит за экран.
    function setClosedState(closed) {
      if ('inert' in HTMLElement.prototype) {
        nav.inert = closed;
      } else {
        links.forEach(function (link) { link.tabIndex = closed ? -1 : 0; });
      }
    }

    function isCollapsed() {
      return getComputedStyle(burger).display !== 'none';
    }

    function open() {
      document.body.classList.add('nav-open');
      burger.setAttribute('aria-expanded', 'true');
      setClosedState(false);
      // Панель показывается через visibility, поэтому фокус ставим после
      // пересчёта стилей: focus() на visibility:hidden молча не срабатывает.
      requestAnimationFrame(function () { if (links[0]) links[0].focus(); });
    }

    function close(restoreFocus) {
      document.body.classList.remove('nav-open');
      burger.setAttribute('aria-expanded', 'false');
      setClosedState(isCollapsed());
      if (restoreFocus) burger.focus();
    }

    burger.addEventListener('click', function () {
      if (document.body.classList.contains('nav-open')) close(true);
      else open();
    });

    nav.addEventListener('click', function (event) {
      if (event.target.closest('a')) close(false);
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && document.body.classList.contains('nav-open')) close(true);
    });

    // Фокус не должен уходить из открытой панели на контент за ней.
    document.addEventListener('focusin', function (event) {
      if (!document.body.classList.contains('nav-open')) return;
      if (nav.contains(event.target) || event.target === burger) return;
      if (links[0]) links[0].focus();
    });

    // Переход между мобильной и десктопной раскладкой не должен оставлять
    // страницу в промежуточном состоянии.
    var sync = function () {
      if (!isCollapsed()) close(false);
      setClosedState(isCollapsed() && !document.body.classList.contains('nav-open'));
    };
    window.addEventListener('resize', sync, { passive: true });
    sync();
  }

  /* ── Подсветка текущего раздела ──────────────────────────────────── */
  function initScrollSpy() {
    if (!('IntersectionObserver' in window)) return;
    var links = Array.prototype.slice.call(document.querySelectorAll('.nav a[href^="#"]'));
    var sections = links
      .map(function (link) { return document.querySelector(link.getAttribute('href')); })
      .filter(Boolean);
    if (!sections.length) return;

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

  initContacts();
  initMenuTabs();
  initNav();
  initScrollSpy();
  initYear();
})();
