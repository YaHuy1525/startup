module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src'],
  testMatch: ['**/__tests__/**/*.ts', '**/?(*.)+(spec|test).ts'],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'json'],
  collectCoverageFrom: [
    'src/**/*.ts',
    'src/**/*.tsx',
    '!src/**/*.d.ts',
  ],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', {
      tsconfig: {
        jsx: 'react',
        esModuleInterop: true,
        allowSyntheticDefaultImports: true,
      }
    }]
  },
  transformIgnorePatterns: [
    'node_modules/(?!(@remotion|remotion)/)',
  ],
  moduleNameMapper: {
    '^remotion$': '<rootDir>/node_modules/remotion',
    '^@remotion/(.*)$': '<rootDir>/node_modules/@remotion/$1',
  },
  testTimeout: 30000, // 30 seconds for video rendering tests
};
