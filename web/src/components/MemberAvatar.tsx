"use client";

import { useState } from "react";

export default function MemberAvatar({
  photoUrl,
  initials,
  partyClass,
  large,
  name,
}: {
  photoUrl: string | null;
  initials: string;
  partyClass: string;
  large?: boolean;
  name: string;
}) {
  const [failed, setFailed] = useState(false);
  const className = `member-avatar ${partyClass}${large ? " member-avatar--lg" : ""}`;

  if (photoUrl && !failed) {
    return (
      <img
        src={photoUrl}
        alt={name}
        className={`${className} member-avatar--photo`}
        onError={() => setFailed(true)}
      />
    );
  }
  return <div className={className}>{initials}</div>;
}
