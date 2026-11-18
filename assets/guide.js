/* Generated: tools/build_ui.py */
(function () {
	'use strict';
	const links = document.querySelectorAll('.guide-toc a');
	function highlightSection() {
		for (const link of links) {
			if (link.hash === location.hash) link.setAttribute('aria-current', 'location');
			else link.removeAttribute('aria-current');
		}
	}
	addEventListener('hashchange', highlightSection);
	highlightSection();
}());
