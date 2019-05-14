import { RemoteChannelResource, TaskResource } from 'kolibri.resources';
import { ErrorTypes } from '../../constants';
import { waitForTaskToComplete } from '../manageContent/utils';
import { getChannelWithContentSizes } from './apiChannelMetadata';

/**
 * Makes request to RemoteChannel API with a token. Does not actually interact
 * with Vuex store.
 *
 * @param {string} token -
 * @returns Promise
 */
export function getRemoteChannelByToken(token) {
  return RemoteChannelResource.fetchModel({ id: token, force: true });
}

export function getRemoteChannelBundleByToken(token) {
  return RemoteChannelResource.fetchChannelList(token);
}

/**
 * Starts Tasks that either downloads a Channel Metadata database,
 * or annotate the content importability for the current import method
 * NOTE: cannot be normally dispatched as an action, since it uses
 * waitForTaskToComplete (which relies on the store singleton with a .watch method)
 *
 */
export function readyChannelMetadata(store, download = true) {
  const { transferredChannel, selectedDrive, selectedPeer } = store.state.manageContent.wizard;
  let promise;
  if (download) {
    if (store.getters['manageContent/wizard/inLocalImportMode']) {
      promise = TaskResource.startDiskChannelImport({
        channel_id: transferredChannel.id,
        drive_id: selectedDrive.id,
      });
    } else if (store.getters['manageContent/wizard/inRemoteImportMode']) {
      promise = TaskResource.startRemoteChannelImport({
        channel_id: transferredChannel.id,
      });
    } else if (store.getters['manageContent/wizard/inPeerImportMode']) {
      promise = TaskResource.startRemoteChannelImport({
        channel_id: transferredChannel.id,
        baseurl: selectedPeer.base_url,
      });
    } else if (store.getters['manageContent/wizard/inExportMode']) {
      return getChannelWithContentSizes(transferredChannel.id);
    } else {
      return Error('Channel Metadata is only downloaded when importing');
    }
  } else {
    if (store.getters['manageContent/wizard/inLocalImportMode']) {
      promise = TaskResource.startAnnotateImportability({
        channel_id: transferredChannel.id,
        drive_id: selectedDrive.id,
      });
    } else if (store.getters['manageContent/wizard/inRemoteImportMode']) {
      promise = TaskResource.startAnnotateImportability({
        channel_id: transferredChannel.id,
      });
    } else if (store.getters['manageContent/wizard/inPeerImportMode']) {
      promise = TaskResource.startAnnotateImportability({
        channel_id: transferredChannel.id,
        baseurl: selectedPeer.base_url,
      });
    } else if (store.getters['manageContent/wizard/inExportMode']) {
      return getChannelWithContentSizes(transferredChannel.id);
    } else {
      return Error('Channel Metadata is only downloaded when importing');
    }
  }
  promise = promise.catch(() => Promise.reject({ errorType: ErrorTypes.CONTENT_DB_LOADING_ERROR }));

  return promise
    .then(task => {
      // NOTE: store.watch is not available to dispatched actions
      return waitForTaskToComplete(store, task.entity.id);
    })
    .then(completedTask => {
      const { taskId, cancelled } = completedTask;
      if (taskId && !cancelled) {
        return TaskResource.deleteFinishedTasks().then(() => {
          return getChannelWithContentSizes(transferredChannel.id);
        });
      }
      return Promise.reject({ errorType: ErrorTypes.CHANNEL_TASK_ERROR });
    });
}

export function calculateApproximateCounts(duplicateResources, count) {
  // If we have duplicate resources
  // then our counts are estimates so we return
  // a rounded estimate of what the actual count is
  if (duplicateResources > 1) {
    // Round the counts to a precision of 2 significant figures.
    // Round up any non-integer part - round up to ensure that we never
    // return a value of zero if the input was greater than zero.
    return Math.ceil(Number.parseFloat(count / duplicateResources).toPrecision(2));
  } else {
    return count;
  }
}

export function calculateApproximateFileSize(duplicateFiles, fileSize) {
  // If we have duplicate files
  // then our file sizes are estimates so we return
  // an estimate of what the actual file size is
  if (duplicateFiles > 1) {
    return fileSize / duplicateFiles;
  } else {
    return fileSize;
  }
}
