type SectionNode = {
  id: string;
  parent_id: string | null;
};

function parentSectionIds<T extends SectionNode>(sections: readonly T[]): Set<string> {
  return new Set(sections.flatMap((section) => section.parent_id ? [section.parent_id] : []));
}

export function isAssignableSection<T extends SectionNode>(
  section: T,
  sections: readonly T[],
): boolean {
  return !parentSectionIds(sections).has(section.id);
}

export function assignableSections<T extends SectionNode>(sections: readonly T[]): T[] {
  const parentIds = parentSectionIds(sections);
  return sections.filter((section) => !parentIds.has(section.id));
}
