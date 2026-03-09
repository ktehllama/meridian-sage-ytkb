/**
 * unicornEmbed(snippet, targetEl, options)
 *
 * Paste the raw Unicorn Studio embed snippet, get a watermark-free,
 * centered scene injected into any element.
 *
 * Options:
 *   cropPx      {number}  px to crop from bottom to hide badge (default: 85)
 *   credit      {string}  optional subtle text credit e.g. 'Made with Unicorn Studio'
 *   creditColor {string}  credit color (default: 'rgba(255,255,255,0.25)')
 */
function unicornEmbed(snippet, targetEl, options) {
  options = options || {};
  var cropPx      = options.cropPx      !== undefined ? options.cropPx : 85;
  var credit      = options.credit      || null;
  var creditColor = options.creditColor || 'rgba(255,255,255,0.25)';

  var parser   = new DOMParser();
  var doc      = parser.parseFromString(snippet, 'text/html');
  var embedDiv = doc.querySelector('[data-us-project]');

  if (!embedDiv) {
    console.error('unicornEmbed: no [data-us-project] found in snippet');
    return;
  }

  var projectId = embedDiv.getAttribute('data-us-project');
  var rawW      = embedDiv.style.width  || '100%';
  var rawH      = embedDiv.style.height || '100%';
  var hNum      = parseInt(rawH, 10);

  var wrapper = document.createElement('div');
  Object.assign(wrapper.style, {
    position: 'relative',
    width:    '100%',
    height:   '100%',
    overflow: 'hidden',
    display:  'block',
  });

  var inner = document.createElement('div');
  inner.setAttribute('data-us-project', projectId);
  Object.assign(inner.style, {
    position:  'absolute',
    top:       '0',
    left:      '50%',
    transform: 'translateX(-50%)',
    width:     rawW,
    height:    !isNaN(hNum) ? (hNum + cropPx) + 'px' : 'calc(' + rawH + ' + ' + cropPx + 'px)',
  });

  var attrs = embedDiv.attributes;
  for (var i = 0; i < attrs.length; i++) {
    var a = attrs[i];
    if (a.name.startsWith('data-us-') && a.name !== 'data-us-project') {
      inner.setAttribute(a.name, a.value);
    }
  }

  wrapper.appendChild(inner);

  if (credit) {
    var creditEl = document.createElement('div');
    creditEl.textContent = credit;
    Object.assign(creditEl.style, {
      position:      'absolute',
      bottom:        '12px',
      left:          '50%',
      transform:     'translateX(-50%)',
      color:         creditColor,
      fontSize:      '10px',
      fontFamily:    'system-ui, sans-serif',
      letterSpacing: '0.06em',
      zIndex:        '10',
      pointerEvents: 'none',
      userSelect:    'none',
      whiteSpace:    'nowrap',
    });
    wrapper.appendChild(creditEl);
  }

  targetEl.innerHTML = '';
  targetEl.appendChild(wrapper);

  if (!document.getElementById('_us_no_badge')) {
    var style = document.createElement('style');
    style.id = '_us_no_badge';
    style.textContent = 'a[href*="unicorn.studio?utm_source=public-url"]{display:none!important}';
    document.head.appendChild(style);
  }

  function initSDK() {
    if (window.UnicornStudio && window.UnicornStudio.init) {
      window.UnicornStudio.init();
      return;
    }
    window.UnicornStudio = { isInitialized: false };
    var script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/gh/hiunicornstudio/unicornstudio.js@v2.1.3/dist/unicornStudio.umd.js';
    script.onload = function () { window.UnicornStudio.init(); };
    (document.head || document.body).appendChild(script);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSDK);
  } else {
    initSDK();
  }
}

export default unicornEmbed;
