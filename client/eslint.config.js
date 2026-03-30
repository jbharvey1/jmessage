import baseConfig from '../../core/react/eslint.config.base.js';
import globals from 'globals';

export default [
    ...baseConfig,
    {
        languageOptions: {
            globals: globals.browser,
        },
    },
    { ignores: ['dist/', 'build/'] },
];
