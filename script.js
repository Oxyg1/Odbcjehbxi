/* =========================================================
   Траттория «Pro Italia», Калуга — скрипты лендинга
   Без зависимостей. Всё работает при открытии index.html из файла.

   Содержание:
   1. Хедер: фон при скролле
   2. Бургер-меню
   3. Подсветка активного пункта меню
   4. Появление секций при скролле (IntersectionObserver)
   5. Галерея: лайтбокс
   6. Форма бронирования: маска телефона + валидация + отправка
   7. Мелочи: год в футере
   ========================================================= */

(function () {
  'use strict';

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- 1. Хедер: фон при скролле ---------- */
  var header = document.getElementById('header');

  function updateHeader() {
    if (!header) return;
    header.classList.toggle('is-scrolled', window.scrollY > 40);
  }

  updateHeader();
  window.addEventListener('scroll', updateHeader, { passive: true });

  /* ---------- 2. Бургер-меню ---------- */
  var burger = document.getElementById('burger');
  var nav = document.getElementById('nav');

  function closeNav() {
    if (!burger || !nav) return;
    nav.classList.remove('is-open');
    burger.setAttribute('aria-expanded', 'false');
    burger.setAttribute('aria-label', 'Открыть меню');
    document.body.classList.remove('is-locked');
  }

  function toggleNav() {
    if (!burger || !nav) return;
    var willOpen = !nav.classList.contains('is-open');
    nav.classList.toggle('is-open', willOpen);
    burger.setAttribute('aria-expanded', String(willOpen));
    burger.setAttribute('aria-label', willOpen ? 'Закрыть меню' : 'Открыть меню');
    document.body.classList.toggle('is-locked', willOpen);
  }

  if (burger) burger.addEventListener('click', toggleNav);

  // Закрываем меню после клика по ссылке и при возврате на десктоп
  if (nav) {
    nav.addEventListener('click', function (e) {
      if (e.target.closest('a')) closeNav();
    });
  }
  window.addEventListener('resize', function () {
    if (window.innerWidth > 860) closeNav();
  });

  /* ---------- 3. Подсветка активного пункта меню ---------- */
  var navLinks = Array.prototype.slice.call(document.querySelectorAll('.nav__link'));
  var sections = navLinks
    .map(function (link) { return document.querySelector(link.getAttribute('href')); })
    .filter(Boolean);

  if ('IntersectionObserver' in window && sections.length) {
    var navObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        navLinks.forEach(function (link) {
          link.classList.toggle('is-active', link.getAttribute('href') === '#' + entry.target.id);
        });
      });
    }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });

    sections.forEach(function (section) { navObserver.observe(section); });

    // На первом экране ни один пункт меню не подсвечиваем
    window.addEventListener('scroll', function () {
      if (window.scrollY > 120) return;
      navLinks.forEach(function (link) { link.classList.remove('is-active'); });
    }, { passive: true });
  }

  /* ---------- 4. Появление секций при скролле ---------- */
  var revealItems = document.querySelectorAll('.reveal');

  if (!('IntersectionObserver' in window) || reduceMotion) {
    // Фолбэк: просто показываем всё
    Array.prototype.forEach.call(revealItems, function (el) { el.classList.add('is-visible'); });
  } else {
    var revealObserver = new IntersectionObserver(function (entries, observer) {
      entries.forEach(function (entry, i) {
        if (!entry.isIntersecting) return;
        // Лёгкая «лесенка» для карточек, попавших в кадр одновременно
        entry.target.style.transitionDelay = Math.min(i * 70, 280) + 'ms';
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.08 });

    Array.prototype.forEach.call(revealItems, function (el) { revealObserver.observe(el); });
  }

  /* ---------- 5. Галерея: лайтбокс ---------- */
  var lightbox = document.getElementById('lightbox');
  var lightboxImg = document.getElementById('lightboxImg');
  var lightboxCaption = document.getElementById('lightboxCaption');
  var lightboxClose = document.getElementById('lightboxClose');
  var lightboxPrev = document.getElementById('lightboxPrev');
  var lightboxNext = document.getElementById('lightboxNext');
  var galleryItems = Array.prototype.slice.call(document.querySelectorAll('.gallery__item'));
  var currentIndex = 0;
  var lastFocused = null;

  function showImage(index) {
    if (!galleryItems.length) return;
    currentIndex = (index + galleryItems.length) % galleryItems.length;
    var img = galleryItems[currentIndex].querySelector('img');
    if (!img) return;
    lightboxImg.src = img.currentSrc || img.src;
    lightboxImg.alt = img.alt;
    lightboxCaption.textContent = img.alt + ' — ' + (currentIndex + 1) + ' из ' + galleryItems.length;
  }

  function openLightbox(index) {
    lastFocused = document.activeElement;
    showImage(index);
    lightbox.hidden = false;
    document.body.classList.add('is-locked');
    lightboxClose.focus();
  }

  function closeLightbox() {
    lightbox.hidden = true;
    lightboxImg.src = '';
    document.body.classList.remove('is-locked');
    if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
  }

  galleryItems.forEach(function (item, index) {
    item.addEventListener('click', function () { openLightbox(index); });
  });

  if (lightbox) {
    lightboxClose.addEventListener('click', closeLightbox);
    lightboxPrev.addEventListener('click', function () { showImage(currentIndex - 1); });
    lightboxNext.addEventListener('click', function () { showImage(currentIndex + 1); });

    // Клик по затемнённому фону закрывает просмотр
    lightbox.addEventListener('click', function (e) {
      if (e.target === lightbox || e.target.classList.contains('lightbox__figure')) closeLightbox();
    });

    document.addEventListener('keydown', function (e) {
      if (lightbox.hidden) {
        if (e.key === 'Escape') closeNav();
        return;
      }
      if (e.key === 'Escape') closeLightbox();
      if (e.key === 'ArrowLeft') showImage(currentIndex - 1);
      if (e.key === 'ArrowRight') showImage(currentIndex + 1);
      // Простая «ловушка» фокуса внутри лайтбокса
      if (e.key === 'Tab') {
        var focusable = [lightboxClose, lightboxPrev, lightboxNext];
        var pos = focusable.indexOf(document.activeElement);
        e.preventDefault();
        var nextPos = e.shiftKey ? pos - 1 : pos + 1;
        focusable[(nextPos + focusable.length) % focusable.length].focus();
      }
    });

    // Свайпы на мобильных
    var touchStartX = null;
    lightbox.addEventListener('touchstart', function (e) {
      touchStartX = e.changedTouches[0].clientX;
    }, { passive: true });
    lightbox.addEventListener('touchend', function (e) {
      if (touchStartX === null) return;
      var delta = e.changedTouches[0].clientX - touchStartX;
      if (Math.abs(delta) > 50) showImage(currentIndex + (delta < 0 ? 1 : -1));
      touchStartX = null;
    }, { passive: true });
  }

  /* ---------- 6. Форма бронирования ---------- */
  var form = document.getElementById('bookingForm');

  if (form) {
    var phoneInput = document.getElementById('phone');
    var dateInput = document.getElementById('date');
    var statusEl = document.getElementById('formStatus');
    var submitBtn = document.getElementById('submitBtn');

    // Нельзя выбрать дату в прошлом
    if (dateInput) {
      var today = new Date();
      var localToday = new Date(today.getTime() - today.getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 10);
      dateInput.min = localToday;
      if (!dateInput.value) dateInput.value = localToday;
    }

    /* Маска телефона: +7 (999) 123-45-67 */
    function formatPhone(value) {
      var digits = value.replace(/\D/g, '');
      if (!digits) return '';
      // 8XXXXXXXXXX и 7XXXXXXXXXX приводим к одному виду
      if (digits[0] === '8' || digits[0] === '7') digits = digits.slice(1);
      digits = digits.slice(0, 10);

      var out = '+7';
      if (digits.length) out += ' (' + digits.slice(0, 3);
      if (digits.length >= 4) out += ') ' + digits.slice(3, 6);
      if (digits.length >= 7) out += '-' + digits.slice(6, 8);
      if (digits.length >= 9) out += '-' + digits.slice(8, 10);
      return out;
    }

    if (phoneInput) {
      phoneInput.addEventListener('input', function () {
        phoneInput.value = formatPhone(phoneInput.value);
      });
      phoneInput.addEventListener('focus', function () {
        if (!phoneInput.value) phoneInput.value = '+7 (';
      });
      phoneInput.addEventListener('blur', function () {
        if (phoneInput.value.replace(/\D/g, '').length <= 1) phoneInput.value = '';
      });
    }

    // Ссылка на политику лежит внутри <label> — без этого клик по ней
    // заодно переключал бы галочку согласия
    var consentLink = form.querySelector('.checkbox a');
    if (consentLink) {
      consentLink.addEventListener('click', function (e) { e.stopPropagation(); });
    }

    function setError(field, message) {
      var wrapper = field.closest('.field') || field.closest('.checkbox');
      var errorEl = document.getElementById(field.id + '-error');
      if (wrapper) wrapper.classList.toggle('has-error', Boolean(message));
      if (errorEl) errorEl.textContent = message || '';
      field.setAttribute('aria-invalid', message ? 'true' : 'false');
      return !message;
    }

    var validators = {
      name: function (v) {
        if (!v.trim()) return 'Пожалуйста, представьтесь';
        if (v.trim().length < 2) return 'Слишком короткое имя';
        return '';
      },
      phone: function (v) {
        var digits = v.replace(/\D/g, '');
        if (!digits) return 'Укажите телефон для подтверждения брони';
        if (digits.length !== 11) return 'Введите номер полностью: +7 (___) ___-__-__';
        return '';
      },
      date: function (v) {
        if (!v) return 'Выберите дату визита';
        var chosen = new Date(v + 'T00:00:00');
        var now = new Date();
        now.setHours(0, 0, 0, 0);
        if (chosen < now) return 'Дата уже прошла';
        return '';
      },
      time: function (v) {
        if (!v) return 'Выберите время';
        return '';
      },
      guests: function (v) {
        if (!v) return 'Укажите количество гостей';
        return '';
      },
      consent: function (v, field) {
        if (!field.checked) return 'Без согласия мы не сможем принять заявку';
        return '';
      }
    };

    function validateField(field) {
      var validate = validators[field.id];
      if (!validate) return true;
      return setError(field, validate(field.value, field));
    }

    // Убираем ошибку, как только гость начал исправлять поле
    Object.keys(validators).forEach(function (id) {
      var field = document.getElementById(id);
      if (!field) return;
      var eventName = field.type === 'checkbox' || field.tagName === 'SELECT' ? 'change' : 'input';
      field.addEventListener(eventName, function () {
        var wrapper = field.closest('.field') || field.closest('.checkbox');
        if (wrapper && wrapper.classList.contains('has-error')) validateField(field);
      });
      field.addEventListener('blur', function () { validateField(field); });
    });

    function showStatus(message, isError) {
      statusEl.textContent = message;
      statusEl.classList.add('is-visible');
      statusEl.classList.toggle('is-error', Boolean(isError));
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();

      statusEl.classList.remove('is-visible', 'is-error');
      statusEl.textContent = '';

      var firstInvalid = null;
      Object.keys(validators).forEach(function (id) {
        var field = document.getElementById(id);
        if (!field) return;
        if (!validateField(field) && !firstInvalid) firstInvalid = field;
      });

      if (firstInvalid) {
        firstInvalid.focus({ preventScroll: true });
        firstInvalid.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' });
        showStatus('Проверьте отмеченные поля — и отправим заявку.', true);
        return;
      }

      var data = {
        name: document.getElementById('name').value.trim(),
        phone: document.getElementById('phone').value.trim(),
        date: document.getElementById('date').value,
        time: document.getElementById('time').value,
        guests: document.getElementById('guests').value,
        comment: document.getElementById('comment').value.trim()
      };

      submitBtn.disabled = true;
      submitBtn.textContent = 'Отправляем…';

      /* -----------------------------------------------------------------
         ЗДЕСЬ ПОДКЛЮЧАЕТСЯ РЕАЛЬНАЯ ОТПРАВКА ЗАЯВКИ.
         Сейчас работает демо-режим: заявка никуда не уходит.

         Вариант 1 — Formspree / Getform (без своего бэкенда):
           fetch('https://formspree.io/f/ВАШ_ID', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
             body: JSON.stringify(data)
           }).then(handleSuccess).catch(handleError);

         Вариант 2 — Telegram-бот (токен держите на своём сервере-прокси,
         в открытом коде сайта его публиковать нельзя):
           fetch('/api/booking', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify(data)
           }).then(handleSuccess).catch(handleError);

         Вариант 3 — обычный PHP-обработчик на хостинге: POST на /booking.php
         ----------------------------------------------------------------- */

      window.setTimeout(function () {
        console.info('Заявка на бронь (демо-режим, отправка не настроена):', data);

        submitBtn.disabled = false;
        submitBtn.textContent = 'Отправить заявку';

        showStatus(
          'Спасибо, ' + data.name + '! Заявка принята — мы перезвоним на ' + data.phone +
          ', чтобы подтвердить столик ' + formatDateRu(data.date) + ' в ' + data.time + '.'
        );

        form.reset();
        if (dateInput) dateInput.value = dateInput.min;
        statusEl.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' });
      }, 600);
    });

    function formatDateRu(value) {
      var parts = value.split('-');
      if (parts.length !== 3) return value;
      var months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
      return parseInt(parts[2], 10) + ' ' + months[parseInt(parts[1], 10) - 1];
    }
  }

  /* ---------- 7. Статус «сейчас открыто» ----------
     Считаем по московскому времени, чтобы гость из другого часового пояса
     видел корректный статус. Расписание — в минутах от начала суток;
     закрытие в 00:00 = 1440 (конец тех же суток, ночного перехода нет). */
  var SCHEDULE = [
    { open: 9 * 60, close: 23 * 60 },  // воскресенье
    { open: 8 * 60, close: 23 * 60 },  // понедельник
    { open: 8 * 60, close: 23 * 60 },  // вторник
    { open: 8 * 60, close: 23 * 60 },  // среда
    { open: 8 * 60, close: 23 * 60 },  // четверг
    { open: 8 * 60, close: 24 * 60 },  // пятница
    { open: 9 * 60, close: 24 * 60 }   // суббота
  ];

  function formatTime(minutes) {
    var h = Math.floor(minutes / 60) % 24;
    var m = minutes % 60;
    return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
  }

  function getMoscowTime() {
    try {
      var parts = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Europe/Moscow',
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      }).formatToParts(new Date());

      var map = {};
      parts.forEach(function (part) { map[part.type] = part.value; });

      var days = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
      var day = days[map.weekday];
      if (day === undefined) return null;

      return { day: day, minutes: (parseInt(map.hour, 10) % 24) * 60 + parseInt(map.minute, 10) };
    } catch (e) {
      return null; // Intl без поддержки таймзон — просто не показываем статус
    }
  }

  var statusBox = document.getElementById('workStatus');

  function updateWorkStatus() {
    if (!statusBox) return;
    var now = getMoscowTime();
    if (!now) return;

    var today = SCHEDULE[now.day];
    var isOpen = now.minutes >= today.open && now.minutes < today.close;
    var text;

    if (isOpen) {
      text = 'Сейчас открыто · до ' + formatTime(today.close);
    } else if (now.minutes < today.open) {
      text = 'Сейчас закрыто · откроем сегодня в ' + formatTime(today.open);
    } else {
      text = 'Сейчас закрыто · откроем завтра в ' + formatTime(SCHEDULE[(now.day + 1) % 7].open);
    }

    statusBox.textContent = text;
    statusBox.classList.toggle('is-closed', !isOpen);
    statusBox.hidden = false;
  }

  updateWorkStatus();
  window.setInterval(updateWorkStatus, 60000);

  /* ---------- 8. Мелочи ---------- */
  var yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());
})();
