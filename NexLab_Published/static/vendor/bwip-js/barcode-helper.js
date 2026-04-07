/**
 * Local Barcode Generator - uses bwip-js for 100% offline barcode generation
 * Include bwip-js before this script: <script src="/static/vendor/bwip-js/bwip-js.min.js"></script>
 */
function generateBarcodeDataURL(text, scale, height, includeText) {
    try {
        var canvas = document.createElement('canvas');
        bwipjs.toCanvas(canvas, {
            bcid: 'code128',
            text: text || '',
            scale: scale || 3,
            height: height || 10,
            includetext: includeText !== false,
            textxalign: 'center',
        });
        return canvas.toDataURL('image/png');
    } catch (e) {
        console.error('Barcode generation error:', e);
        return '';
    }
}

function renderBarcodeToElement(el, text, scale, height, includeText) {
    try {
        var canvas = document.createElement('canvas');
        bwipjs.toCanvas(canvas, {
            bcid: 'code128',
            text: text || '',
            scale: scale || 3,
            height: height || 10,
            includetext: includeText !== false,
            textxalign: 'center',
        });
        canvas.style.maxWidth = '100%';
        canvas.style.height = 'auto';
        canvas.style.display = 'block';
        el.innerHTML = '';
        el.style.textAlign = 'center';
        el.style.padding = '5px';
        el.appendChild(canvas);
    } catch (e) {
        console.error('Barcode render error:', e);
        el.innerHTML = '<span style="color:red;font-size:10px;">Barcode Error</span>';
    }
}
