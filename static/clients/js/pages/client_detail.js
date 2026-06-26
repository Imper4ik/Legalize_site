document.addEventListener('DOMContentLoaded', function () {
    var params = new URLSearchParams(window.location.search);
    if (params.get('tab') === 'history' || window.location.hash === '#communication-history') {
      var trigger = document.getElementById('history-tab');
      if (trigger && window.bootstrap) {
        window.bootstrap.Tab.getOrCreateInstance(trigger).show();
      }
    }
  });
