const MOCK_DEFAULTS = {
  facilityConfig: {},
  selectedFacility: {},
  facilities: [],
  facilityId: '',
  userIsMultiFacilityAdmin: false,
  getFacilities: jest.fn(),
  getFacilityConfig: jest.fn(),
  setFacilityConfig: jest.fn(),
  setFacilities: jest.fn(),
  checkFacilityExists: jest.fn(),
  getMinimalFacilities: jest.fn(),
};

export function useFacilitiesMock(overrides = {}) {
  return {
    ...MOCK_DEFAULTS,
    ...overrides,
  };
}

export default jest.fn(() => useFacilitiesMock());
