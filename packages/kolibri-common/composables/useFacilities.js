import { ref, computed } from 'vue';
import FacilityResource from 'kolibri-common/apiResources/FacilityResource';
import useUser from 'kolibri/composables/useUser';
import redirectBrowser from 'kolibri/utils/redirectBrowser';
import FacilityDatasetResource from 'kolibri-common/apiResources/FacilityDatasetResource';
import Lockr from 'lockr';
import store from 'kolibri/store';
import client from 'kolibri/client';
import urls from 'kolibri/urls';

const _facilityConfig = ref({});
const _facilities = ref([]);
const _facilityId = ref(Lockr.get('facilityId') || null);

export default function useFacilities() {
  const { userFacilityId, isSuperuser } = useUser();

  // const route = router.currentRoute;
  const selectedFacility = computed(() => {
    const facilityById = _facilities.value.find(f => f.id === _facilityId.value);
    if (facilityById) {
      return facilityById;
    }
    return _facilities.value.find(f => f.id === userFacilityId.value) || null;
  });

  //getters
  const facilities = computed(() => _facilities.value);
  const facilityConfig = computed(() => _facilityConfig.value);
  const userIsMultiFacilityAdmin = computed(() => {
    return isSuperuser.value && _facilities.value.length > 1;
  });
  const currentFacilityName = computed(() => {
    const match = _facilities.value.find(f => f.id === store.getters.activeFacilityId);
    return match ? match.name : '';
  });

  //actions
  async function getFacilities() {
    const facilities = await FacilityResource.fetchCollection({ force: true });

    _facilities.value = facilities;
  }

  async function getFacilityConfig(facilityId) {
    const facId = facilityId || userFacilityId.value;

    if (!facId) {
      // No facility Id, so redirect and let Kolibri sort it out
      return redirectBrowser();
    }

    let facilityConfig;

    if (selectedFacility.value && typeof selectedFacility.value.dataset !== 'object') {
      facilityConfig = [selectedFacility.value.dataset];
    } else {
      facilityConfig = await FacilityDatasetResource.fetchCollection({
        getParams: {
          facility_id: facId,
        },
      });
    }

    let config = {};
    const facility = facilityConfig[0];

    if (facility) {
      config = { ...facility };
    }
    setFacilityConfig(config);
  }

  async function checkFacilityExists() {
    const url = urls['kolibri:kolibri.plugins.facility:facility-exists']();
    const response = await client.get(url);
    return response.data.exists; // "none" | "single" | "multiple"
  }

  async function getMinimalFacilities() {
    const url = urls['kolibri:kolibri.plugins.facility:facility-names']();
    const response = await client.get(url);
    _facilities.value = response.data;
    return _facilities.value;
  }

  //mutations
  function setFacilityConfig(facilityConfig) {
    _facilityConfig.value = facilityConfig;
  }

  function setFacilities(facilities) {
    _facilities.value = facilities;
  }

  function setFacilityId(facilityId) {
    _facilityId.value = facilityId;
  }

  return {
    facilities,
    facilityConfig,
    getFacilities,
    getFacilityConfig,
    setFacilityConfig,
    setFacilities,
    selectedFacility,
    userIsMultiFacilityAdmin,
    currentFacilityName,
    setFacilityId,
    checkFacilityExists,
    getMinimalFacilities,
  };
}
