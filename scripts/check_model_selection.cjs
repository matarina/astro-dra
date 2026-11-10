// Exercise the deployed form code without a browser or a real user database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const overlay = path.join(__dirname, '../local_deep_research/overlay');
const requests = [];
const errors = [];
const controls = {};
function control(value = '') {
    return {value, dataset: {}, disabled: true, style: {}, listeners: {},
        addEventListener(type, fn) {
            (this.listeners[type] ||= []).push(fn);
        },
        change() { for (const fn of this.listeners.change || []) fn.call(this); }
    };
}
controls.model_provider = control('OPENAI_ENDPOINT');
controls.model_provider.options = [
    {value: 'OPENAI_ENDPOINT'}, {value: 'LLAMACPP'}, {value: 'OPENAI', disabled: true}
];
controls.model = control();
controls.model_hidden = control();
controls.search_engine_hidden = control('pubmed');
const sourceModels = [
    {id: 'deepseek-v4-flash', name: 'DeepSeek', provider: 'OPENAI_ENDPOINT'},
    {id: 'qwen-gguf', name: 'Qwen Flash', provider: 'LLAMACPP'}
];
const context = vm.createContext({
    console, setTimeout, clearTimeout,
    SafeLogger: {log() {}, warn() {}, error(...args) {errors.push(args);}},
    URLS: {SETTINGS_API: {BASE: '/settings'}, API: {START_RESEARCH: '/start'}},
    URLBuilder: {progressPage: id => `/progress/${id}`},
    window: {
        safeUpdateButton() {}, location: {}, RESEARCH_STATUS: {QUEUED: 'queued'},
        createSafeLoadingOverlay: () => ({style: {}})
    },
    document: {
        addEventListener() {}, body: {appendChild() {}},
        getElementById: id => controls[id] || null,
        querySelector: selector => controls[selector.slice(1)] || null,
        querySelectorAll: () => []
    },
    fetch(url, options = {}) {
        requests.push({url, ...options});
        return Promise.resolve({ok: true, json: async () => url === '/settings' ? {
            settings: {
                'llm.provider': {value: 'openai_endpoint', editable: false},
                'llm.model': {value: 'deepseek-v4-flash', editable: false}
            }
        } : {status: 'success', research_id: 'test'}});
    }
});
let code = fs.readFileSync(path.join(overlay, 'research.js'), 'utf8');
code = code.replace("    document.addEventListener('DOMContentLoaded', initializeResearch);", `
    globalThis.test = {
        prepare(elements, models) {
            modelProviderSelect = elements.model_provider;
            modelInput = elements.model;
            queryInput = {value: 'A biomedical research question', addEventListener() {}};
            form = {addEventListener() {}};
            startBtn = {};
            modeOptions = [];
            cacheData(CACHE_KEYS.MODELS, models);
            onInitializationComplete = () => {};
        },
        loadSettings, setupEventListeners, saveModelSettings, handleResearchSubmit,
        getSelection: () => selectedModelValue
    };
`);
vm.runInContext(code, context);
vm.runInContext(fs.readFileSync(path.join(overlay, 'settings_sync.js'), 'utf8'), context);
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
    context.test.prepare(controls, sourceModels);
    context.test.loadSettings();
    await settle();
    assert.equal(controls.model_provider.value, 'OPENAI_ENDPOINT');
    assert.equal(controls.model_hidden.value, 'deepseek-v4-flash');
    assert.equal(controls.model_provider.disabled, false);
    assert.equal(controls.model.disabled, false);
    assert.equal(controls.model_provider.options[2].disabled, true);
    context.test.setupEventListeners();
    context.connectMenuSettings();
    requests.length = 0;
    controls.model_provider.value = 'LLAMACPP';
    controls.model_provider.change();
    await settle();
    assert.equal(context.test.getSelection(), '', 'Old provider model must be cleared');
    assert.equal(controls.model_hidden.value, '', 'Submit must not reuse the old provider model');
    // Model dropdown writes the exact model ID to the hidden form input.
    controls.model_hidden.value = 'qwen-gguf';
    controls.model_hidden.change();
    context.test.saveModelSettings('qwen-gguf');
    assert.equal(requests.length, 0, 'Both settings handlers must preserve deployment defaults');
    context.test.handleResearchSubmit({preventDefault() {}});
    await settle();
    const submitted = requests.find(r => r.url === '/start');
    assert.ok(submitted);
    const payload = JSON.parse(submitted.body);
    assert.equal(payload.model_provider, 'LLAMACPP');
    assert.equal(payload.model, 'qwen-gguf');
    assert.equal(payload.search_engine, 'pubmed');
    assert.deepEqual(errors, []);
    console.log('PASS: deployment defaults restored, model/provider selectable, egress-disabled option retained, stale selection cleared, no locked-setting writes, Qwen request payload correct.');
})().catch(error => {console.error(error); process.exitCode = 1;});
