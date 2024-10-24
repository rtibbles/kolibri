import orderBy from 'lodash/orderBy';
import { computed, getCurrentInstance } from '@vue/composition-api';

export default function useQuizzes(store) {
  store = store || getCurrentInstance().proxy.$store;
  const quizzes = computed(() =>
    orderBy(store.getters['classSummary/exams'], 'date_created', 'desc'),
  );
  const fetchQuizSizes = () => store.dispatch('classSummary/fetchQuizzesSizes');

  return {
    quizzes,
    fetchQuizSizes,
  };
}
