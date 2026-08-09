import js from '@eslint/js'
import typescriptEslint from '@typescript-eslint/eslint-plugin'
import typescriptParser from '@typescript-eslint/parser'
import perfectionist from 'eslint-plugin-perfectionist'
import reactPlugin from 'eslint-plugin-react'
import reactCompiler from 'eslint-plugin-react-compiler'
import hooksPlugin from 'eslint-plugin-react-hooks'
import unusedImports from 'eslint-plugin-unused-imports'
import globals from 'globals'

const noopRule = {
  meta: { schema: [], type: 'problem' },
  create: () => ({})
}

const customRules = {
  rules: {
    'no-process-cwd': noopRule,
    'no-process-env-top-level': noopRule,
    'no-sync-fs': noopRule,
    'no-top-level-dynamic-import': noopRule,
    'no-top-level-side-effects': noopRule
  }
}

export default [
  {
    ignores: ['**/node_modules/**', '**/dist/**', 'src/**/*.js']
  },
  js.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node
      },
      parser: typescriptParser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        ecmaVersion: 'latest',
        sourceType: 'module'
      }
    },
    plugins: {
      '@typescript-eslint': typescriptEslint,
      'custom-rules': customRules,
      perfectionist,
      react: reactPlugin,
      'react-compiler': reactCompiler,
      'react-hooks': hooksPlugin,
      'unused-imports': unusedImports
    },
    rules: {
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
      '@typescript-eslint/no-unused-vars': 'off',
      curly: ['error', 'all'],
      'no-fallthrough': ['error', { allowEmptyCase: true }],
      'no-undef': 'off',
      'no-unused-vars': 'off',
      'padding-line-between-statements': [
        1,
        {
          blankLine: 'always',
          next: [
            'block-like',
            'block',
            'return',
            'if',
            'class',
            'continue',
            'debugger',
            'break',
            'multiline-const',
            'multiline-let'
          ],
          prev: '*'
        },
        {
          blankLine: 'always',
          next: '*',
          prev: ['case', 'default', 'multiline-const', 'multiline-let', 'multiline-block-like']
        },
        { blankLine: 'never', next: ['block', 'block-like'], prev: ['case', 'default'] },
        { blankLine: 'always', next: ['block', 'block-like'], prev: ['block', 'block-like'] },
        { blankLine: 'always', next: ['empty'], prev: 'export' },
        { blankLine: 'never', next: 'iife', prev: ['block', 'block-like', 'empty'] }
      ],
      'perfectionist/sort-exports': ['error', { order: 'asc', type: 'natural' }],
      'perfectionist/sort-imports': [
        'error',
        {
          groups: ['side-effect', 'builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          order: 'asc',
          type: 'natural'
        }
      ],
      'perfectionist/sort-jsx-props': ['error', { order: 'asc', type: 'natural' }],
      'perfectionist/sort-named-exports': ['error', { order: 'asc', type: 'natural' }],
      'perfectionist/sort-named-imports': ['error', { order: 'asc', type: 'natural' }],
      'react-compiler/react-compiler': 'warn',
      'react-hooks/exhaustive-deps': 'warn',
      'react-hooks/rules-of-hooks': 'error',
      'unused-imports/no-unused-imports': 'error'
    },
    settings: {
      react: { version: 'detect' }
    }
  },
  {
    files: ['**/*.js', '**/*.cjs'],
    ignores: ['**/node_modules/**', '**/dist/**'],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: { ...globals.node },
      sourceType: 'commonjs'
    }
  },
  {
    // The bundled studio (src/app/image-studio/**) is .jsx, which flat config
    // does not pick up by default — it was linted by nothing at all, which is
    // how `makeGenerationStartCallback` (crashed the whole studio) and a
    // missing `toast` import shipped. Correctness rules only: the tree is
    // vendored, so the stylistic/sorting rules above would be pure noise.
    files: ['**/*.jsx'],
    ignores: ['**/node_modules/**', '**/dist/**'],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { ecmaFeatures: { jsx: true } },
      sourceType: 'module'
    },
    // react-hooks is registered so the tree's inline
    // `eslint-disable-next-line react-hooks/exhaustive-deps` comments resolve
    // instead of erroring with "Definition for rule was not found".
    plugins: { react: reactPlugin, 'react-hooks': hooksPlugin },
    rules: {
      'no-undef': 'error',
      // The rules below come from js.configs.recommended and flag stylistic
      // patterns that are pervasive in this vendored tree (48 pre-existing
      // hits). Restyling third-party code isn't the goal here — keeping
      // `npm run lint` green while no-undef stays enforced is.
      'no-case-declarations': 'off',
      'no-empty': 'off',
      'no-extra-boolean-cast': 'off',
      'no-prototype-builtins': 'off',
      'no-useless-escape': 'off',
      // Off to match the .ts/.tsx block above — unused locals are style, and on
      // vendored code they drown out the correctness signal we actually want.
      'no-unused-vars': 'off',
      // Without these, every component referenced only inside JSX reads as an
      // unused variable and buries the real no-undef signal.
      'react/jsx-uses-react': 'error',
      'react/jsx-uses-vars': 'error'
    },
    settings: { react: { version: 'detect' } }
  },
  {
    ignores: ['*.config.*']
  }
]
