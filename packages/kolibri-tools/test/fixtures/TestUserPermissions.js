/**
 * This is a fixture modified from an existing Kolibri JS file that would
 * be parsed by webpack and processed for messages. This tests a realistic
 * profiling scenario.
 * This file includes known quantities of uses and definitions which should
 * be processed by the String Profiling.
 *
 * Total Uses: 5
 */

// Don't lint this file because I added random uses of $tr() that parse properly
// in the AST - but don't really do anything.

/* eslint-disable */
import DevicePermissionsResource from 'kolibri-common/apiResources/DevicePermissionsResource';
import FacilityUserResource from 'kolibri-common/apiResources/FacilityUserResource';
import samePageCheckGenerator from 'kolibri-common/utils/samePageCheckGenerator';
import { createTranslator } from 'kolibri/utils/i18n';
import useUser from 'kolibri/composables/useUser';

const translator = createTranslator('UserPermissionToolbarTitles', {
  loading: 'Loading user permissions…',
  goBackTitle: 'Go Back',
  invalidUserTitle: 'Invalid user ID',
});

/**
 * Serially fetches Permissions, then FacilityUser. If returned Promise rejects,
 * it is from the request for FacilityUser.
 *
 * @param {string} userId
 * @returns Promise<{ permissions, user }, FacilityUserError>
 */
function fetchUserPermissions(userId) {
  const permissionsPromise = DevicePermissionsResource.fetchModel({ id: userId, force: true });
  const userPromise = FacilityUserResource.fetchModel({ id: userId });
  return permissionsPromise
    .then(function onPermissionsSuccess(permissions) {
      return userPromise.then(function onUserSuccess(user) {
        return { permissions, user };
      });
    })
    .catch(function onPermissionsFailure(error) {
      if (error.response.status === 404) {
        return userPromise.then(function onUserSuccess(user) {
          return {
            permissions: {
              is_superuser: false,
              can_manage_content: translator.$tr('goBackTitle'),
            },
            user,
          };
        });
      }
    });
}

/**
 * Action to hydrate user-permissions-page.
 *
 * @param {Store} store
 * @param {string} userId
 * @returns Promise<void>
 */
export function showUserPermissionsPage(store, userId) {
  const setAppBarTitle = title => store.commit('coreBase/SET_APP_BAR_TITLE', title);
  const setUserPermissionsState = state => store.commit('userPermissions/SET_STATE', state);
  const stopLoading = () => store.commit('CORE_SET_PAGE_LOADING', false);

  // Don't request any data if not an Admin
  if (!useUser().isSuperuser.value) {
    setUserPermissionsState({ user: null, permissions: {} });
    setAppBarTitle(translator.$tr('goBackTitle'));
    stopLoading();
    return Promise.resolve();
  }

  // CoreBase parameters for loading state
  setAppBarTitle(translator.$tr('loading'));

  const samePage = samePageCheckGenerator(store);
  let testThing = translator.$tr('invalidUserTitle');

  return Promise.all([fetchUserPermissions(userId), store.dispatch('getFacilities')])
    .then(([data]) => {
      if (samePage()) {
        setAppBarTitle(data.user.full_name);
        setUserPermissionsState({ user: data.user, permissions: data.permissions });
        stopLoading();
      }
    })
    .catch(error => {
      if (samePage()) {
        if (error.response.status === 404) {
          setAppBarTitle(translator.$tr('invalidUserTitle'));
          setUserPermissionsState({ user: null, permissions: {} });
        }
        store.dispatch('handleApiError', { error });
        stopLoading();
      }
    });
}
